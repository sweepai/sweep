import socket
import subprocess
import threading
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.responses import HTMLResponse, JSONResponse, Response


def start_redis():
    # redis-server /app/redis.conf --bind 0.0.0.0 --port 6379 &
    import subprocess

    # Check if a screen session named 'redis' already exists
    result = subprocess.run(["screen", "-list"], capture_output=True, text=True)
    if "redis" not in result.stdout:
        # If the session doesn't exist, start redis-server in a new screen session named 'redis'
        subprocess.run(
            [
                "screen",
                "-S",
                "redis",
                "-d",
                "-m",
                "redis-server",
                "redis.conf",
                "--bind",
                "0.0.0.0",
                "--port",
                "6379",
            ]
        )
        print("Started redis server")
    else:
        print("A screen session with the name 'redis' already exists.")


start_redis()

app = FastAPI()

TARGET_SERVER = (
    "http://0.0.0.0:{port}"  # Replace with the URL of the server you want to forward to
)

port_offset = 9000
screen_prefix = "sweep"
current_port = None

current_index = 0
used_indices = []

kill_flag_times = {}
max_time = 30 * 60  # 20 minutes


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.bind(("0.0.0.0", port))
            return False
        except socket.error:
            return True


def get_next_port():
    global current_index
    while is_port_in_use(port_offset + current_index):
        current_index += 1


get_next_port()
print("Starting on port:", port_offset + current_index)


def kill_old_server(index):
    # Signal the old server to stop
    global used_indices
    print(index, used_indices, index in used_indices)
    if index in used_indices:
        print("Flagged for deletion:", f"{screen_prefix}{index}.run")
        kill_flag_times[index] = time.time()
        used_indices.remove(index)


def check_killed_servers():
    # for each server, check if it's been killed
    keys_to_remove = []

    for index, kill_time in kill_flag_times.items():
        if time.time() - kill_time > max_time:
            print("Killing", f"{screen_prefix}{index}")
            subprocess.run(
                ["screen", "-S", f"{screen_prefix}{index}.run", "-X", "stuff", "\003"]
            )
            time.sleep(30)
            subprocess.run(
                ["screen", "-S", f"{screen_prefix}{index}.run", "-X", "quit"]
            )
            keys_to_remove.append(index)

    # Remove the collected keys from the dictionary
    for key in keys_to_remove:
        kill_flag_times.pop(key, None)


def update_port(new_port):
    # Thread sleep
    import time

    time.sleep(15)
    global current_port
    current_port = new_port
    print("New port has been updated:", current_port)


def start_server(past_index):
    print("STARTING")

    global current_index, current_port, used_indices
    new_port = port_offset + current_index
    subprocess.run(
        [
            "screen",
            "-S",
            f"{screen_prefix}{current_index}.run",
            "-d",
            "-m",
            "bash",
            "-c",
            f"export PORT={new_port} && docker compose -p sweep{new_port} up",
        ]
    )
    kill_old_server(past_index)
    threading.Thread(target=check_killed_servers).start()
    used_indices.append(current_index)
    update_port(new_port)


# screen -S hi -d -m bash -c "sleep 10; echo hi"
@app.get("/proxy_start")
async def start_endpoint():
    # Create new asyncio loop
    global current_index
    past_index = current_index
    current_index += 1
    get_next_port()

    threading.Thread(target=start_server, args=(past_index,)).start()
    return {
        "session": f"{screen_prefix}{current_index}.run",
        "port": port_offset + current_index,
    }


@app.middleware("http")
async def reroute_request(request: Request, call_next):
    global current_port
    # Reroute to proxy controls
    if "/proxy_" in request.url.path:
        return await call_next(request)

    if current_port is None:
        return Response(
            content="Server is starting up", media_type="text/plain", status_code=503
        )

    async with httpx.AsyncClient() as client:
        # Capture original request data
        data = await request.body()
        headers = dict(request.headers)

        # Exclude certain headers to avoid issues with forwarding
        exclude_headers = ["host", "connection", "accept-encoding"]
        for header in exclude_headers:
            headers.pop(header, None)

        try:
            # Forward the request to the target server
            response = await client.request(
                request.method,
                f"{TARGET_SERVER.format(port=current_port)}{request.url.path}",
                data=data,
                headers=headers,
                params=request.query_params,
            )

            content_type = response.headers.get("content-type")

            # Depending on the content type, wrap the bytes response in an appropriate FastAPI response class
            if "json" in content_type:
                return JSONResponse(content=response.json())
            elif "html" in content_type:
                return HTMLResponse(content=response.text)
            else:
                return Response(content=response.content, media_type=content_type)

        except httpx.RequestError as exc:
            raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
