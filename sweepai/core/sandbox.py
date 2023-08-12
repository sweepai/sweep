import asyncio

from e2b import Session
from pydantic import BaseModel
from typing import Type, TypeVar


Self = TypeVar("Self", bound="Sandbox")


REPO_PATH = "~/repo"
GIT_PASS = 'cd ~; echo \'#!/bin/sh\\necho "{token}"\' > git-askpass.sh && chmod +x git-askpass.sh'
GIT_CLONE = "cd ~; export GIT_ASKPASS=./git-askpass.sh;" \
            "git config --global credential.helper 'cache --timeout=3600';" \
            "git clone https://{username}@github.com/{repo} " + REPO_PATH
PYTHON_CREATE_VENV = f"cd {REPO_PATH} && python3 -m venv venv && source venv/bin/activate && poetry install"


# Class for ShellMessage
class ShellMessage(BaseModel):
    message: str
    error: bool = False


class Sandbox(BaseModel):
    username: str
    token: str
    image: str = "Python3"
    session: Session

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    async def from_token(cls: Type[Self], username: str, token: str, **kwargs) -> Self:
        image = kwargs.get("image", "Nodejs")
        session = Session(image)
        await session.open()

        sandbox = cls(
            username=username,
            token=token,
            image=image,
            session=session
        )
        #await sandbox.run_command(HOME_DIR_PERM)
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

    async def create_python_venv(self):
        await self.run_command(PYTHON_CREATE_VENV)

    async def close(self):
        await self.session.close()
