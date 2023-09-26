import json
import os
from dataclasses import dataclass

import modal

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
        "curl -fsSL https://deb.nodesource.com/setup_18.x | bash -",
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
class InstallSetup:
    lang: str
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

    def get_lint_scripts(self, repo: str = "./repo"):
        scripts = []
        if self.lang == "js":
            tsconfig_path = os.path.join(repo, "tsconfig.json")
            if os.path.exists(tsconfig_path):
                scripts.append("tsc")
            package_json = json.load(open(os.path.join(repo, "package.json")))
            if "lint" in package_json.get("scripts", []):
                scripts.append("lint")
            scripts = [f"{self.name} run {script}" for script in scripts]
        return scripts


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


install_setup = detect_install_setup("test_repos/landing-page")
print(install_setup.get_lint_scripts("./test_repos/landing-page"))


@stub.local_entrypoint()
def run_sandbox(
    timeout: int = 90,
):
    # sandbox: Sandbox = Sandbox(
    #     install_command="yarn install --ignore-engines",
    #     formatter_command="yarn run prettier --write",
    #     linter_command="yarn lint && yarn run tsc",
    # )
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        f"cd landing-page && (yarn run --prettier check . || (exit_code=$?; if [ $exit_code -eq 2 ]; then exit 2; fi; exit 0)) && yarn run lint && yarn run tsc",
        image=god_image.copy_local_file(
            "test_repos/landing-page/package.json", "./landing-page/package.json"
        ).run_commands("cd landing-page && yarn install --ignore-engines"),
        mounts=[modal.Mount.from_local_dir("test_repos/landing-page")],
        timeout=timeout,
    )

    sb.wait()
    print(sb.returncode)

    if sb.returncode != 0:
        # raise Exception(sb.stdout.read() + "\n\n" + sb.stderr.read())
        # print(sb.stdout.read())
        print(sb.stderr.read())
        print("Error!")
    else:
        return sb.stdout.read()
