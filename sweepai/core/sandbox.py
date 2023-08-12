import asyncio

from e2b import Session
from loguru import logger
from pydantic import BaseModel
from typing import Type, TypeVar

from sweepai.config.client import get_sandbox_config, SweepConfig

Self = TypeVar("Self", bound="Sandbox")


REPO_PATH = "~/repo"
GIT_PASS = 'cd ~; echo \'#!/bin/sh\\necho "{token}"\' > git-askpass.sh && chmod +x git-askpass.sh'
GIT_CLONE = "cd ~; export GIT_ASKPASS=./git-askpass.sh;" \
            "git config --global credential.helper 'cache --timeout=3600';" \
            "git clone https://{username}@github.com/{repo} " + REPO_PATH
GIT_BRANCH = f"cd {REPO_PATH}; " + "checkout -B {branch}"
IMAGE_INSTALLATION = {
    "Nodejs": f"cd {REPO_PATH}; npm install",
}
PYTHON_CREATE_VENV = f"cd {REPO_PATH} && python3 -m venv venv && source venv/bin/activate && poetry install"


class Sandbox(BaseModel):
    username: str
    token: str
    format_command: str = None
    linter_command: str = None
    image: str = "Python3"
    session: Session

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    async def from_token(cls: Type[Self], username: str, token: str, repo) -> Self | None:
        config = get_sandbox_config(repo)
        enabled = config.get("enabled", False)
        image = config.get("image", None)
        formatter = config.get("formatter", None)
        linter = config.get("linter", None)
        main_branch = SweepConfig.get_branch(repo)

        if not enabled:  # Sandbox is not enabled
            logger.info("Sandbox is not enabled")
            return None
        if image is None or IMAGE_INSTALLATION.get(image) is None:  # No image specified
            return None
        if formatter is None and linter is None:  # No need to create a sandbox if there is no formatter or linter
            return None

        session = Session(image)
        await session.open()
        sandbox = cls(
            username=username,
            token=token,
            image=image,
            session=session,
            format_command=f'cd {REPO_PATH}; formatter',
            linter_command=f'cd {REPO_PATH}; linter',
        )

        await sandbox.clone_repo()
        await sandbox.update_branch(main_branch)
        await sandbox.run_command(IMAGE_INSTALLATION[image])
        return sandbox

    async def run_command(self, command: str):
        print("Running command", command)
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
        await self.session.filesystem.write(f'{REPO_PATH}/{file_path}', content)
        # Fix permissions
        await self.run_command(f"sudo chmod 777 {REPO_PATH}/{file_path}")

    async def read_repo_file(self, file_path):
        return await self.session.filesystem.read(f'{REPO_PATH}/{file_path}')

    async def run_formatter(self, file_path, content):
        await self.write_repo_file(file_path, content)
        await self.run_command(self.format_command)
        return await self.read_repo_file(file_path)

    async def run_linter(self):
        if self.linter_command is None:
            return None
        await self.run_command(self.linter_command)

    async def close(self):
        await self.session.close()
