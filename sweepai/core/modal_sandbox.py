from dataclasses import dataclass
import modal
from pydantic import BaseModel

from sweepai.core.sandbox import Sandbox

stub = modal.Stub("api")

god_image = (
    modal.Image.debian_slim()
    .apt_install(
        # Basics
        "git",
        "curl",
    )
    .run_commands(
        # Install Node & npm
        "curl -fsSL https://deb.nodesource.com/setup_18.x | -E bash -",
        "apt install nodejs",
    )
    .run_commands(
        # Install yarn
        "curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -",
        'echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list',
        "apt update",
        "apt install yarn",
    )
    # .run_commands("curl -fsSL https://get.pnpm.io/install.sh | sh -")
    .pip_install(["pre-commit", "pylint", "black"])
)


@dataclass
class SandboxError(Exception):
    stdout: str
    stderr: str


def run_sandbox(
    sandbox: Sandbox,
    timeout: int = 120,
):
    print(sandbox.linter_command)
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        f"cd repo && {sandbox.linter_command}",
        # image=god_image,
        image=god_image.copy_local_file(
            "repo/package.json", "repo/package.json"
        ).run_commands(f"cd repo && {sandbox.install_command}"),
        mounts=[modal.Mount.from_local_dir("repo")],
        timeout=timeout,
    )

    sb.wait()
    print("RETURN CODE: " + str(sb.returncode))

    print("STDOUT:", sb.stdout.read())
    print("STDERR:", sb.stderr.read())
    if sb.returncode != 0:
        raise SandboxError(sb.stdout.read(), sb.stderr.read())
    else:
        return sb.stdout.read()
