from dataclasses import dataclass
import json
import os
import io
import tarfile
import uuid
import requests

import shlex
from fastapi import FastAPI, Request
from pydantic import BaseModel
import docker

from sweepai.config.server import DISCORD_WEBHOOK_URL

from src.chat import fix_file
from src.sandbox_utils import Sandbox

from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import FastAPI, Request

app = FastAPI()

client = docker.from_env()

class SandboxContainer:
    def __init__(self, *args, **kwargs):
        self.container_name = "sandbox-{}".format(str(uuid.uuid4()))

    def __enter__(self):
        client.containers.run("sandbox", "tail -f /dev/null", detach=True, name=self.container_name) # keeps the container running
        self.container = client.containers.get(self.container_name)
        return self.container

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.container.stop()
        self.container.remove(force=True)

def write_file(container, file_path, content):
    # Convert the content to bytes
    content_bytes = content.encode('utf-8')

    tar_stream = io.BytesIO()
    with tarfile.TarFile(fileobj=tar_stream, mode='w') as tar:
        file_data = tarfile.TarInfo(name=file_path.split('/')[-1])  # Use only the filename, not the full path
        file_data.size = len(content_bytes)
        tar.addfile(file_data, io.BytesIO(content_bytes))

    # Ensure directories exist
    directory = os.path.dirname(file_path)
    container.exec_run(f'mkdir -p {directory}', user='root')  # Execute the mkdir command within the container

    tar_stream.seek(0)
    container.put_archive(os.path.dirname(file_path), tar_stream)


def read_file(container, file_path):
    # Get a tarball of the file from the container
    tar_stream, _ = container.get_archive(file_path)

    # Create a BytesIO object from the tar stream
    tar_byte_stream = io.BytesIO()
    for chunk in tar_stream:
        tar_byte_stream.write(chunk)

    # Set the stream position to the beginning
    tar_byte_stream.seek(0)

    # Extract the file content from the tarball
    with tarfile.TarFile(fileobj=tar_byte_stream) as tar:
        member = tar.next()  # Get the first (and only) member in the tarball
        if member is not None:
            file_content = tar.extractfile(member).read()
            return file_content.decode('utf-8')

    return None 

trunk_setup_commands = [
    "cd repo && ls",
    "cd repo && trunk init && npm init -y && npm install --force prettier",
    "cd repo && npx prettier --write {file_path}"
]

def discord_log_error(content, priority=0):
    """
    priority: 0 (high), 1 (medium), 2 (low)
    """
    if DISCORD_WEBHOOK_URL:
        try:
            data = {"content": content}
            headers = {"Content-Type": "application/json"}
            response = requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(data), headers=headers)
            print(response)
            # Success: response.status_code == 204:
        except Exception as e:
            print(f"Could not log to Discord: {e}")


sandboxes: dict[str, Sandbox] = {}

class SandboxRequest(BaseModel):
    repo_url: str
    file_path: str
    content: str
    token: str | None = None

@app.get("/health")
def health_check():
    return JSONResponse(status_code=200, content={"status": "UP"})

@app.get("/", response_class=HTMLResponse)
def home():
    return "<h2>Sweep Sandbox is up and running!</h2>"

@dataclass
class SandboxError(Exception):
    message: str

@app.post("/sandbox")
async def run_sandbox(request: Request):
    data = await request.json()
    sandbox_request = SandboxRequest(**data)
    print(sandbox_request.repo_url, sandbox_request.file_path, sandbox_request.token)
    correct_key = None
    repo_full_name = "/".join(sandbox_request.repo_url.split('/')[-2:])
    for key in sandboxes.keys():
        if repo_full_name.startswith(key):
            correct_key = key
            break
    sandbox = sandboxes.get(correct_key, Sandbox())
    
    try:
        if sandbox_request.token:
            sandbox_request.repo_url = sandbox_request.repo_url.replace("://", f"://x-access-token:{sandbox_request.token}@")
            print(sandbox_request.repo_url)

        with SandboxContainer() as container:
            print("Cloning repo...")
            exit_code, output = container.exec_run(f"git clone {sandbox_request.repo_url} repo")
            write_file(container, f'repo/{sandbox_request.file_path}', sandbox_request.content)
            print(f"Git Clone - Exit Code: {exit_code}")
            print(output.decode('utf-8'))

            print("Running sandbox...")
            error_message = ""
            success, error_messages, updated_content = False, [], ""

            def wrap_command(command):
                command = shlex.quote("cd repo && " + command.format(file_path=sandbox_request.file_path))
                return f"bash -c {command}"
            
            def run_command(command):
                print(f"\n\n### Running {command} ###\n")
                exit_code, output = container.exec_run(wrap_command(command), stderr=True)
                output = output.decode('utf-8')
                # print(output)
                output_lines = output.split('\n')
                print("\n".join(output_lines[:5]) + "\n...\n" + "\n".join(output_lines[-5:]))
                if exit_code != 0 and not ("prettier" in command and exit_code == 2):
                    raise Exception(output)
                return output

            # Install dependencies
            run_command(sandbox.install_command)

            num_iterations = 15
            for i in range(1, num_iterations + 1):
                try:
                    print(f"Trying to lint for the {i}/{num_iterations}th time")
                    for command in sandbox.linter_command:
                        run_command(command)
                except Exception as e:
                    error_message = str(e)
                    if len(error_messages) >= 2 and error_message == error_messages[-1] and error_message == error_messages[-2]:
                        raise Exception("Failed to fix the code after multiple attempts")
                    error_messages.append(error_message)
                    fixed_code = fix_file(
                        sandbox_request.file_path, 
                        sandbox_request.content, 
                        error_message
                    )
                    write_file(container, f'repo/{sandbox_request.file_path}', fixed_code)
                else:
                    break
            else:
                raise Exception("Failed to fix the code")

            print("Success!")
            run_command(sandbox.format_command)
            success = True

            # Read formatted file
            updated_content = read_file(container, f'repo/{sandbox_request.file_path}')
            print(f"Updated Contents:\n```\n{updated_content}\n```")

    except Exception as e:
        error_message = str(e)
        discord_log_error(f"Error in {sandbox_request.repo_url}:\nfile: {sandbox_request.file_path}\ncontents: {sandbox_request.content}\n\nError messages:\n{error_message}")
        raise e

    return {
        "success": success, 
        "error_messages": error_messages,
        "updated_content": updated_content,
        "sandbox": sandbox.dict(),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)


# uvicorn sandbox_local:app --reload --port 8081
