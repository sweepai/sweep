import os
import yaml
import shlex
import tarfile
import docker 
import typer
from pathlib import Path
from rich import print

from sandbox.src.sandbox_local import SandboxContainer
from sandbox.src.sandbox_utils import Sandbox

client = docker.from_env()

def copy_to(container):
    tar = tarfile.open("repo.tar", mode='w')
    try:
        tar.add(".")
    finally:
        tar.close()

    data = open('repo.tar', 'rb').read()
    container.put_archive(".", data)

def get_sandbox_from_config():
    if os.path.exists("sweep.yaml"):
        config = yaml.load(open("sweep.yaml", "r"), Loader=yaml.FullLoader)
        return Sandbox(**config.get("sweep", {}))
    else:
        return Sandbox()


app = typer.Typer(name="sweep-sandbox")

@app.command()
def sandbox(file_path: Path):
    sandbox = get_sandbox_from_config()
    with SandboxContainer() as container:
        copy_to(container)
        print("Running sandbox...")

        def wrap_command(command):
            command = shlex.quote(command.format(file_path=file_path))
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

        for command in sandbox.linter_command:
            run_command(command)

        print("Success!")
        run_command(sandbox.format_command)

if __name__ == "__main__":
    app()
