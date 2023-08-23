from dataclasses import dataclass
import modal
from pydantic import BaseModel

from sweepai.core.sandbox import Sandbox

stub = modal.Stub("api")

god_image = (
    modal.Image.debian_slim()
    .apt_install(
        # Install npm
        "git",
        "npm",
        "nodejs",
        "curl",
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
    timeout: int = 90,
):
    print(sandbox.linter_command)
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        f"cd repo; {sandbox.install_command}; {sandbox.linter_command}",
        image=god_image,
        mounts=[modal.Mount.from_local_dir("repo")],
        timeout=timeout,
    )

    sb.wait()
    print("RETURN CODE: " + sb.returncode)

    if sb.returncode != 0:
        raise SandboxError(sb.stdout.read(), sb.stderr.read())
    else:
        return sb.stdout.read()
