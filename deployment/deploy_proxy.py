from time import time
from fastapi import FastAPI, Request, HTTPException
from starlette.responses import Response, JSONResponse, HTMLResponse
import httpx
import subprocess

app = FastAPI()

TARGET_SERVER = (
    "http://0.0.0.0:8080"  # Replace with the URL of the server you want to forward to
)

screen_prefix = "sweep"
current_index = 0

kill_flag_times = {}
max_time = 0.2 * 60  # 20 minutes


def kill_old_server(index):
    # Signal the old server to stop
    print("Stopping", f"{screen_prefix}{current_index}")
    kill_flag_times[index] = time()


def check_killed_servers():
    # for each server, check if it's been killed
    keys_to_remove = []

    for index, kill_time in kill_flag_times.items():
        if time() - kill_time > max_time:
            print("Killing", f"{screen_prefix}{index}")
            subprocess.run(["screen", "-S", f"{screen_prefix}{index}", "-X", "quit"])
            keys_to_remove.append(index)

    # Remove the collected keys from the dictionary
    for key in keys_to_remove:
        kill_flag_times.pop(key, None)


def start_server():
    print("STARTING")

    global current_index
    past_index = current_index
    current_index += 1
    subprocess.run(
        [
            "screen",
            "-S",
            f"{screen_prefix}{current_index}",
            "-d",
            "-m",
            "bash",
            "-c",
            "echo 'hi' && sleep 1000",
        ]
    )
    kill_old_server(past_index)
    check_killed_servers()


# screen -S hi -d -m bash -c "sleep 10; echo hi"
@app.get("/proxy_start")
async def start_endpoint():
    start_server()


@app.middleware("http")
async def reroute_request(request: Request, call_next):
    # Reroute to proxy controls
    if "/proxy_" in request.url.path:
        return await call_next(request)

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
                f"{TARGET_SERVER}{request.url.path}",
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

    uvicorn.run(app, host="0.0.0.0", port=8000)
