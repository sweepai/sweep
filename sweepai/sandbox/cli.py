import os
import shlex
import subprocess
import tarfile
import uuid
from pathlib import Path
from typing import Optional

import docker
import pathspec
import typer
import yaml
from posthog import Posthog
from pydantic import BaseModel
from rich import console
from tqdm import tqdm

class SandboxContainer:
    def __init__(self, *args, **kwargs):
        self.container_name = "sandbox-{}".format(str(uuid.uuid4()))

    def __enter__(self):
        client.containers.run(
            "sweepai/sandbox:latest",
            "tail -f /dev/null",
            detach=True,
            name=self.container_name,
        )  # keeps the container running
        self.container = client.containers.get(self.container_name)
        return self.container

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.container.stop()
        self.container.remove(force=True)


class Sandbox(BaseModel):
    install: list[str] = ["trunk init"]
    check: list[str] = [
        "trunk fmt {file_path}",
        "trunk check --fix --print-failures {file_path}",
    ]
    
    @classmethod
    def validate_yaml(cls, path: str) -> bool: 
        try:
            subprocess.run(["yamllint", path], check=True)
            return True 
        except subprocess.CalledProcessError:
            return False

    @classmethod
    def from_yaml(cls, yaml_string: str):
        config = yaml.load(yaml_string, Loader=yaml.FullLoader)
        return cls(**config.get("sandbox", {}))

    @classmethod
    def from_config(cls, path: str = "sweep.yaml"):
        if os.path.exists(path):
            if not cls.validate_yaml(path):
                raise ValueError("The YAML File is not valid") 
            return cls.from_yaml(open(path).read())
        else:
            return cls()


app = typer.Typer(name="sweep-sandbox")

posthog = Posthog(
    project_api_key="phc_CnzwIB0W548wN4wEGeRuxXqidOlEUH2AcyV2sKTku8n",
    host="https://app.posthog.com",
)

console = console.Console()
print = console.print

client = docker.from_env()


def copy_to(container):
    try:
        spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern,
            open(".gitignore").read().splitlines(),
        )
    except FileNotFoundError:
        spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, [])
    files_to_copy = (
        f
        for f in tqdm(
            Path(".").rglob("*"),
            desc="Getting files to copy",
        )
        if f.is_file() and not spec.match_file(f)
    )

    print("Copying files to container...")
    pbar = tqdm(files_to_copy)
    with tarfile.open("repo.tar", "w") as tar:
        for f in pbar:
            tar.add(f)

    data = open("repo.tar", "rb").read()
    container.exec_run("mkdir repo")
    container.put_archive("repo", data)
    os.remove("repo.tar")


def get_sandbox_from_config():
    if os.path.exists("sweep.yaml"):
        config = yaml.load(open("sweep.yaml", "r"), Loader=yaml.FullLoader)
        return Sandbox(**config.get("sandbox", {}))
    else:
        return Sandbox()


@app.command()
def sandbox(file_path: Optional[Path] = None, telemetry: bool = True):
    # Check if valid git repo
    if not os.path.exists(".git"):
        print("Not a valid git repository", style="bold red")
        raise typer.Exit(code=1)

    print("")

    # Get last edited file
    if file_path is None:
        file_path = Path(
            subprocess.check_output(
                "git diff --name-only HEAD~1 HEAD | head -n 1", shell=True
            )
            .decode("utf-8")
            .strip()
        )
        print(
            f"File path was not provided, so we default to the last edited file [bold]{file_path}[/bold]\n"
        )

    print(" Getting sandbox config... \n", style="bold white on cyan")
    sandbox = get_sandbox_from_config()

    if telemetry:
        try:
            current_dir = os.getcwd()
            dir_name = os.path.basename(current_dir)
            username = uuid.UUID(int=uuid.getnode())
            metadata = {
                "file_path": str(file_path),
                "dir_name": dir_name,
                "install": sandbox.install,
                "check": sandbox.check,
            }
            posthog.capture(username, "sandbox-cli-started", properties=metadata)
        except SystemExit:
            raise SystemExit
        except Exception:
            print("Could not get metadata for telemetry", style="bold red")

    print("Running sandbox with the following settings:\n", sandbox)
    print(f"\n Spinning up sandbox container \n", style="bold white on cyan")
    with SandboxContainer() as container:
        try:
            print(f"[bold]Copying files into sandbox[/bold]")
            copy_to(container)

            def wrap_command(command):
                command = shlex.quote(
                    "cd repo && " + command.format(file_path=file_path)
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

            def run_command(command):
                print(f"\n[bold]Running `{command}`[/bold]\n")
                exit_code, output = container.exec_run(
                    wrap_command(command), stderr=True
                )
                output = output.decode("utf-8")
                if output:
                    print(summarize_logs(output))
                if exit_code != 0 and not ("prettier" in command and exit_code == 2):
                    raise Exception(output)
                return output

            print("\n Running installation scripts... ", style="bold white on cyan")
            for command in sandbox.install:
                run_command(command)

            print("\n Running linter scripts... ", style="bold white on cyan")
            for command in sandbox.check:
                run_command(command)

            print("Success!", style="bold green")

            if telemetry:
                try:
                    posthog.capture(
                        username, "sandbox-cli-success", properties=metadata
                    )
                except SystemExit:
                    raise SystemExit
                except Exception:
                    print("Could not get metadata for telemetry", style="bold red")
        except SystemExit:
            raise SystemExit
        except Exception as e:
            print(f"Error: {e}", style="bold red")
            raise e


if __name__ == "__main__":
    app()
