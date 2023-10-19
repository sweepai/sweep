import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import traceback
import uuid
from dataclasses import asdict, dataclass, field

import docker
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel
from src.chat import fix_file
from src.sandbox_container import SandboxContainer
from src.sandbox_utils import Sandbox
from tqdm import tqdm

app = FastAPI()

client = docker.from_env()


@dataclass
class SandboxExecution:
    command: str
    output: str
    exit_code: int
    stage: str = "check"
    iteration: int = 0


def write_file(container, file_path: str, content: str):
    content_bytes = content.encode("utf-8")

    tar_stream = io.BytesIO()
    with tarfile.TarFile(fileobj=tar_stream, mode="w") as tar:
        file_data = tarfile.TarInfo(name=file_path.split("/")[-1])
        file_data.size = len(content_bytes)
        tar.addfile(file_data, io.BytesIO(content_bytes))

    directory = os.path.dirname(file_path)
    container.exec_run(f"mkdir -p {directory}", user="root")

    tar_stream.seek(0)
    container.put_archive(os.path.dirname(file_path), tar_stream)


def read_file(container: str, file_path: str):
    tar_stream, _ = container.get_archive(file_path)

    tar_byte_stream = io.BytesIO()
    for chunk in tar_stream:
        tar_byte_stream.write(chunk)

    tar_byte_stream.seek(0)

    with tarfile.TarFile(fileobj=tar_byte_stream) as tar:
        member = tar.next()  # Get the first (and only) member in the tarball
        if member is not None:
            file_content = tar.extractfile(member).read()
            return file_content.decode("utf-8")

    return None


def discord_log_error(content, priority=0):
    """
    priority: 0 (high), 1 (medium), 2 (low)
    """
    DISCORD_WEBHOOK_URL = None
    if DISCORD_WEBHOOK_URL:
        try:
            data = {"content": content}
            headers = {"Content-Type": "application/json"}
            response = requests.post(
                DISCORD_WEBHOOK_URL, data=json.dumps(data), headers=headers
            )
            print(response)
            # Success: response.status_code == 204:
        except SystemExit:
            raise SystemExit
        except Exception as e:
            print(f"Could not log to Discord: {e}")


sandboxes: dict[str, Sandbox] = {}


class SandboxRequest(BaseModel):
    repo_url: str
    changed_files: dict[str, str] = {}
    file_path: str | None = None  # if none, only run install step to hydrate cache
    content: str | None = None
    token: str | None = None
    do_fix: bool = True
    # TODO: need branch


@app.get("/health")
def health_check():
    return JSONResponse(status_code=200, content={"status": "UP"})


@app.get("/", response_class=HTMLResponse)
def home():
    return "<h2>Sweep Sandbox is up and running!</h2>"


@dataclass
class SandboxError(Exception):
    message: str


@dataclass
class ClonedRepo:
    repo_full_name: str
    token: str | None = None
    dir_hash: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def dir_path(self):
        return os.path.join("cache/repos", self.repo_full_name, self.dir_hash)

    @property
    def repo_url(self):
        if self.token:
            return (
                f"https://x-access-token:{self.token}@github.com/{self.repo_full_name}/"
            )
        else:
            return f"https://github.com/{self.repo_full_name}/"

    def __post_init__(self):
        subprocess.run(
            ["git", "clone", self.repo_url, self.dir_path, "--depth", "1"], text=True
        )

    def __del__(self):
        try:
            shutil.rmtree(self.dir_path, ignore_errors=True)
        except FileNotFoundError:
            traceback.print_exc()

    @property
    def installation_dict(self):
        # Get all files in root directory that doesn't end in md or rst
        files = [
            f
            for f in tqdm(os.listdir(self.dir_path))
            if not f.endswith((".md", ".rst", ".lock"))
            and os.path.isfile(os.path.join(self.dir_path, f))
        ]
        files_dict = {}
        for file_ in files:
            with open(os.path.join(self.dir_path, file_), "r") as f:
                try:
                    content = f.read()
                    if all(ord(char) < 128 for char in content):  # Check for non-ASCII
                        files_dict[file_] = content
                except UnicodeDecodeError:
                    logger.warning(f"Could not read file {file_}")
        return files_dict

    @property
    def installation_cache_key(self):
        repo_dict = {
            "repo_full_name": self.repo_full_name,
            "files_dict": self.installation_dict,
            "__version__": "0.0.0",
        }
        return hashlib.sha256(
            json.dumps(repo_dict, sort_keys=True).encode("utf-8")
        ).hexdigest()

    @property
    def installation_string(self):
        return f"sandbox/{self.repo_full_name.lower()}:{self.installation_cache_key}"


@app.post("/")
async def run_sandbox(request: SandboxRequest):
    username, repo_name = request.repo_url.split("/")[-2:]
    cloned_repo = ClonedRepo(
        repo_full_name=f"{username}/{repo_name}", token=request.token
    )

    image_id = cloned_repo.installation_string
    image_exists = SandboxContainer.image_exists(image_id)

    success, error_messages, updated_content = False, [], ""
    executions: list[SandboxExecution] = []
    sandbox = Sandbox.from_directory(cloned_repo.dir_path)
    print(f"Running sandbox: {sandbox}...")

    try:
        if request.token:
            request.repo_url = request.repo_url.replace(
                "://", f"://x-access-token:{request.token}@"
            )
            print(request.repo_url)

        if not image_exists:
            sandbox_container = SandboxContainer()
        else:
            sandbox_container = SandboxContainer(image_id=image_id)

        with sandbox_container as container:
            if not image_exists:
                logger.info("Cloning repo...")
                exit_code, output = container.exec_run(
                    f"git clone {request.repo_url} repo --depth 1"
                )
            else:
                logger.info("Using repo from cached image.")
                exit_code, output = container.exec_run(
                    "bash -c "
                    + shlex.quote(
                        f"cd repo && git remote set-url origin https://{request.token}@github.com/{username}/{repo_name}.git && git pull"
                    )
                )

            print(f"Updating git repo - Exit Code: {exit_code}")
            print(output.decode("utf-8"))
            print("Done git pull.")

            error_message = ""

            def wrap_command(command):
                command = shlex.quote(
                    "cd repo && " + command.format(file_path=request.file_path)
                )
                return f"bash -c {command}"

            def summarize_logs(logs):
                output_lines = logs.split("\n")
                if len(output_lines) > 10:
                    return (
                        "\n".join(output_lines[:5])
                        + "\n...\n"
                        + "\n".join(output_lines[-5:])
                    )
                return logs

            def run_command(
                command: str,
                stage: str = "check",
                iteration: int = 0,
                save_execution: bool = True,
            ):
                print(f"\n\n### Running {command} ###\n")
                exit_code, output = container.exec_run(
                    wrap_command(command), stderr=True
                )
                output = output.decode("utf-8")
                print(summarize_logs(output))
                if save_execution:
                    executions.append(
                        SandboxExecution(
                            command=command,
                            output=output,
                            exit_code=exit_code,
                            stage=stage,
                            iteration=iteration,
                        )
                    )
                if exit_code != 0 and not ("prettier" in command and exit_code == 1):
                    raise Exception(output)
                return output

            if not image_exists:
                print("Running installation commands since image not found in cache...")
                for command in sandbox.install:
                    print(command)
                    run_command(command, stage="install")

                print("Committing image...")
                new_image = container.commit()
                new_image.tag(image_id)
            else:
                print("Image already exists, skipping install step...")

            if request.file_path is not None and request.content is not None:
                if request.file_path not in request.changed_files:
                    old_file = ""
                    try:
                        old_file = read_file(container, f"repo/{request.file_path}")
                    except Exception:
                        print("File does not exist, skipping check step...")

                    if old_file:
                        print("Checking file before edit...")
                        for command in sandbox.check:
                            try:
                                run_command(command, stage="check", iteration=0)
                            except Exception as e:
                                print(old_file)
                                raise Exception(
                                    f"File failed to lint with command {command} before edit: {e}"
                                )

                        if request.content == old_file:
                            raise Exception(
                                "New contents are the same as the old contents."
                            )

                for file_path, file_content in request.changed_files.items():
                    print(f"Writing file {file_path}...")
                    write_file(container, f"repo/{file_path}", file_content)

                write_file(container, f"repo/{request.file_path}", request.content)

                if request.do_fix:
                    current_file = request.content
                    num_iterations = 5
                    for i in range(1, num_iterations + 1):
                        try:
                            print(f"Trying to lint for the {i}/{num_iterations}th time")
                            for command in sandbox.check:
                                run_command(command, stage="check", iteration=i)
                        except SystemExit:
                            raise SystemExit
                        except Exception as e:
                            error_message = str(e)
                            if (
                                len(error_messages) >= 2
                                and error_message == error_messages[-1]
                                and error_message == error_messages[-2]
                            ):
                                raise Exception(
                                    "Failed to fix the code after multiple attempts"
                                )
                            error_messages.append(error_message)
                            current_file = fix_file(
                                request.file_path,
                                current_file,
                                error_message,
                                username,
                            )
                            write_file(
                                container, f"repo/{request.file_path}", current_file
                            )
                        else:
                            break
                    else:
                        raise Exception("Failed to fix the code")
                    success = True
                    updated_content = read_file(container, f"repo/{request.file_path}")
                    print(f"Updated Contents:\n```\n{updated_content}\n```")
                else:
                    print("Checking file after edit...")
                    print("Length of content:", len(request.content))
                    current_file = request.content
                    try:
                        print(f"Trying to lint")
                        for command in sandbox.check:
                            run_command(command, stage="check")
                        success = True
                    except Exception as e:
                        error_message = str(e)
                        error_messages.append(error_message)
                        logger.warning(f"Error message: {error_message}")
                    updated_content = read_file(container, f"repo/{request.file_path}")
                    print(f"Updated Contents:\n```\n{updated_content}\n```")
            else:
                success = True
                print("No content provided, skipping edit step...")
    except SystemExit:
        raise SystemExit
    except Exception as e:
        error_message = str(e)
        print(e)
        discord_log_error(
            f"Error in {request.repo_url}:\nFile: {request.file_path}\nContents: {request.content}\n\nError messages:\n{error_message}"
        )

    return {
        "success": success,
        "error_messages": error_messages,
        "outputs": [execution.output for execution in executions],
        "executions": [asdict(execution) for execution in executions],
        "updated_content": updated_content,
        "sandbox": sandbox.dict(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8081)
