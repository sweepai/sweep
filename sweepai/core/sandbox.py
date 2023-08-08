import asyncio

from e2b import Session
from pydantic import BaseModel
from typing import Type, TypeVar


Self = TypeVar("Self", bound="Sandbox")


REPO_PATH = "/code/repo"
GIT_PASS = 'echo \'#!/bin/sh\\necho "{token}"\' > git-askpass.sh && chmod +x git-askpass.sh'
GIT_CLONE = "export GIT_ASKPASS=./git-askpass.sh;" \
            "git config --global credential.helper 'cache --timeout=3600';" \
            "git clone https://{username}@github.com/sweepai-dev/test /code/repo"
PYTHON_CREATE_VENV = "python3 -m venv venv && source venv/bin/activate && poetry install"


# Class for ShellMessage
class ShellMessage(BaseModel):
    message: str
    error: bool = False


class Sandbox(BaseModel):
    username: str
    token: str
    image: str = "Python3"
    session: Session
    path: str = "/code"

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    async def from_token(cls: Type[Self], username: str, token: str, **kwargs) -> Self:
        image = kwargs.get("image", "Python3")
        session = Session(image)
        await session.open()
        return cls(
            username=username,
            token=token,
            image=image,
            session=session
        )

    async def run_command(self, command: str, path: str = None):
        print("Running command", command)
        outputs = []
        proc = await self.session.process.start(
            cmd=command,
            on_stdout=lambda m: outputs.append(ShellMessage(message=m['line'])),
            on_stderr=lambda e: outputs.append(ShellMessage(message=e['line'], error=True)),
            on_exit=lambda: print("Exit"),
            rootdir=path or self.path,
        )
        # await proc.send_stdin("token\n")
        # await proc.kill()
        await proc.finished
        await asyncio.sleep(0.05)  # Small delay to allow the process to finish
        return outputs

    async def clone_repo(self):
        await self.run_command(GIT_PASS.format(token=self.token), path="/code")
        await self.run_command(GIT_CLONE.format(username=self.username), path="/code")
        self.path = REPO_PATH

    async def create_python_venv(self):
        await self.run_command(GIT_PASS.format(token=self.token), path="/code")
