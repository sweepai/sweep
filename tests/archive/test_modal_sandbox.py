import os
import subprocess
from typing import Literal
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
    .pip_install("pre-commit")
)


class InstallSetup(BaseModel):
    name: str
    lang: Literal["py"] | Literal["js"]
    install_script: str
    required_files: list[str]
    _name: str | None = None

    @property
    def name(self):
        return self._name or self.install_script.split()[0]

    def is_used_in(self, file_list: list[str]):
        return all(
            [required_file in file_list for required_file in self.required_files]
        )


class JSInstallSetup(InstallSetup):
    def get_ci_script(repo: str):
        return []


INSTALL_SETUPS = [
    InstallSetup(
        lang="py",
        install_script="pip install -r requirements.txt",
        required_files=["requirements.txt"],
    ),
    InstallSetup(
        lang="py", install_script="poetry install", required_files=["pyproject.toml"]
    ),
    InstallSetup(
        lang="js",
        install_script="npm install",
        required_files=["package.json", "package-lock.json"],
    ),
    InstallSetup(
        lang="js", install_script="yarn", required_files=["package.json", "yarn.lock"]
    ),
    InstallSetup(
        lang="js",
        install_script="pnpm install",
        required_files=["package.json", "pnpm-lock.yaml"],
    ),
]


def detect_install_setup(root="repo"):
    files_in_root = os.listdir(root)
    for install_setup in INSTALL_SETUPS:
        if install_setup.is_used_in(files_in_root):
            return install_setup
    return None


print(detect_install_setup("test_repos/landing-page"))


@stub.local_entrypoint()
def run_sandbox(
    timeout: int = 90,
):
    sandbox: Sandbox = Sandbox(
        install_command="yarn install --ignore-engines",
        formatter_command="yarn run prettier --write",
        linter_command="yarn lint && yarn run tsc",
    )
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        f"cd landing-page && yarn run tsc",
        image=god_image.copy_local_file(
            "test_repos/landing-page/package.json", "./landing-page/package.json"
        ).run_commands(
            "ls landing-page && cd landing-page && yarn install --ignore-engines"
        ),
        mounts=[modal.Mount.from_local_dir("test_repos/landing-page")],
        timeout=timeout,
    )

    sb.wait()
    print(sb.returncode)
    return

    if sb.returncode != 0:
        # raise Exception(sb.stdout.read() + "\n\n" + sb.stderr.read())
        # print(sb.stdout.read())
        print(sb.stderr.read())
        print("Error!")
    else:
        return sb.stdout.read()
