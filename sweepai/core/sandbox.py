import asyncio
import traceback

from e2b import Session
from loguru import logger
from pydantic import BaseModel
from typing import Type, TypeVar, Any

from sweepai.config.client import get_sandbox_config, SweepConfig

Self = TypeVar("Self", bound="Sandbox")


REPO_PATH = "/home/user/repo"
GIT_PASS = "cd ~; echo '#!/bin/sh\\necho \"{token}\"' > git-askpass.sh && chmod ugo+x git-askpass.sh"
GIT_CLONE = (
    "cd ~; export GIT_ASKPASS=./git-askpass.sh;"
    "git config --global credential.helper 'cache --timeout=3600';"
    "git clone https://{username}@github.com/{repo} " + REPO_PATH
)
GIT_BRANCH = f"cd {REPO_PATH}; " + "git checkout -B {branch}"
IMAGE_INSTALLATION = {
    "Nodejs": f"npm install",
}
PYTHON_CREATE_VENV = f"cd {REPO_PATH} && python3 -m venv venv && source venv/bin/activate && poetry install"

LINT_CONFIG = """module.exports = {
    "env": {
        "browser": true,
        "es2021": true
    },
    "extends": [
        "eslint:recommended",
    ],
    "overrides": [
        {
            "env": {
                "node": true
            },
            "files": [
                ".eslintrc.{js,cjs}"
            ],
            "parserOptions": {
                "sourceType": "script"
            }
        }
    ],
    "parserOptions": {
        "ecmaVersion": "latest",
        "sourceType": "module"
    },
    "plugins": [
    ],
    "rules": {
    }
}
"""


class Sandbox(BaseModel):
    username: str
    token: str
    format_command: str = None
    linter_command: str = None
    image: str = "Python3"
    session: Session
    repo: Any

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_token(
        cls: Type[Self], username: str, token: str, repo, config=None
    ) -> Self | None:
        config = config or get_sandbox_config(repo)
        enabled = config.get("enabled", False)
        image = config.get("image", None)
        install_command = config.get("install", IMAGE_INSTALLATION.get(image))
        formatter = config.get("formatter", None)
        linter = config.get("linter", None)

        if not enabled:  # Sandbox is not enabled
            logger.info("Sandbox is not enabled")
            return None
        if image is None or install_command is None:  # No image specified
            logger.info("No image specified")
            return None
        if (
            formatter is None and linter is None
        ):  # No need to create a sandbox if there is no formatter or linter
            logger.info("No formatter or linter specified")
            return None

        print("Created E2B session")
        session = Session(image)
        sandbox = cls(
            username=username,
            token=token,
            image=image,
            session=session,
            format_command=f"cd {REPO_PATH}; {formatter}",
            linter_command=f"cd {REPO_PATH}; {linter}",
            repo=repo,
        )
        print("Created sandbox class")

        return sandbox

    async def start(self):
        config = get_sandbox_config(self.repo)
        main_branch = SweepConfig.get_branch(self.repo)
        image = config.get("image", None)
        install_command = config.get("install", IMAGE_INSTALLATION.get(image))

        print("Starting E2B session")
        await self.session.open()
        print("Cloning repo")
        await self.clone_repo(self.repo.full_name)
        print("Updating branch")
        await self.update_branch(main_branch)
        print("Installing dependencies")
        await self.run_command(f"cd {REPO_PATH}; {install_command}")

    async def run_command(self, command: str):
        print("Running command:", command)
        outputs = []

        def on_stdout(m):
            outputs.append(m)
            print(m.line, m.error)

        proc = await self.session.process.start(
            cmd=command,
            on_stdout=on_stdout,
            on_stderr=on_stdout,
            on_exit=lambda: print("Exit"),
        )
        # await proc.send_stdin("token\n")
        # await proc.kill()
        _ = await proc.finished
        await asyncio.sleep(0.05)  # Small delay to allow the process to finish
        return outputs

    async def clone_repo(self, repo="sweepai/test"):
        await self.run_command(GIT_PASS.format(token=self.token))
        await self.run_command(GIT_CLONE.format(username=self.username, repo=repo))

    async def update_branch(self, branch="main"):
        await self.run_command(GIT_BRANCH.format(branch=branch))

    async def create_python_venv(self):
        await self.run_command(PYTHON_CREATE_VENV)

    async def write_repo_file(self, file_path, content):
        await self.run_command(f"sudo chmod 777 {REPO_PATH}/{file_path}")
        await self.session.filesystem.write(f"{REPO_PATH}/{file_path}", content)
        # Fix permissions
        await self.run_command(f"sudo chmod 777 {REPO_PATH}/{file_path}")

    async def read_repo_file(self, file_path):
        return await self.session.filesystem.read(f"{REPO_PATH}/{file_path}")

    async def run_formatter(self, file_path, content):
        try:
            await self.write_repo_file(file_path, content)
            await self.run_command(
                self.format_command.format(file=file_path, files=file_path)
            )
            return await self.read_repo_file(file_path)
        except Exception as e:
            print("Error running formatter: ", e, "\n")
            print("Trace", traceback.format_exc(), "\n")
            return content

    async def run_linter(self, file_path, content):
        if self.linter_command is None:
            return None

        try:
            await self.session.filesystem.write(
                "/home/user/repo/.eslintrc.js", LINT_CONFIG
            )

            await self.write_repo_file(file_path, content)
            lines = await self.run_command(
                self.linter_command.format(file=file_path, files=file_path)
            )

            # Determine if the linter result contains error

            return lines
        except Exception as e:
            print("Error running formatter: ", e, "\n")
            print("Trace", traceback.format_exc(), "\n")
            return None

    async def formatter_workflow(self, branch, files):
        if len(files) == 0:
            return

        await asyncio.wait_for(self.start(), timeout=60)
        await asyncio.wait_for(
            self.run_command(
                f"cd repo; git fetch; git pull; git checkout {branch}; npm init -y; npm install eslint --save-dev; npm install @typescript-eslint/parser @typescript-eslint/eslint-plugin --save-dev"
            ),
            timeout=60,
        )
        await asyncio.wait_for(
            self.session.filesystem.write("/home/user/repo/.eslintrc.js", LINT_CONFIG),
            timeout=60,
        )

        files_str = '"' + '" "'.join(files) + '"'
        lint_output = await self.run_command("cd repo; npx eslint " + files_str)
        print("E2B:", "\n".join(f.line for f in lint_output))

        await self.close()

        return lint_output

    async def close(self):
        await self.session.close()
