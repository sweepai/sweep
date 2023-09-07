import fnmatch
import os
import yaml
import shlex
import tarfile
import docker 
import typer
from pathlib import Path
from rich import print

from sweepai.sandbox.src.sandbox_local import SandboxContainer
from sweepai.sandbox.src.sandbox_utils import Sandbox

app = typer.Typer(name="sweep-sandbox")

client = docker.from_env()

def copy_to(container):
    try:
        git_ignore_patterns = open('.gitignore').read().splitlines()
    except FileNotFoundError:
        git_ignore_patterns = []
    all_files = set(os.listdir('.'))
    files_to_copy = {f for f in all_files if not any(fnmatch.fnmatch(f, pat) for pat in git_ignore_patterns)}

    with tarfile.open('repo.tar', 'w') as tar:
        for f in files_to_copy:
            tar.add(f)

    data = open('repo.tar', 'rb').read()
    container.put_archive(".", data)
    os.remove("repo.tar")

def get_sandbox_from_config():
    if os.path.exists("sweep.yaml"):
        config = yaml.load(open("sweep.yaml", "r"), Loader=yaml.FullLoader)
        return Sandbox(**config.get("sweep", {}))
    else:
        return Sandbox()

@app.command()
def sandbox(file_path: Path):
    sandbox = get_sandbox_from_config()
    with SandboxContainer() as container:
        # print(container)
        # print(container.exec_run("bash -c trunk"))
        # return
        copy_to(container)
        print("Running sandbox...")

        def wrap_command(command):
            command = shlex.quote(command.format(file_path=file_path))
            print(command)
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
