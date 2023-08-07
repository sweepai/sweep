import asyncio

from e2b import Session
from pydantic import BaseModel
from typing import Type, TypeVar

Self = TypeVar("Self", bound="Sandbox")

GIT_PASS = r'echo \'#!/bin/sh\\necho "{token}"\' > git-askpass.sh && chmod +x git-askpass.sh'
GIT_CLONE = r"export GIT_ASKPASS=./git-askpass.sh;" \
            r"git config --global credential.helper 'cache --timeout=3600';" \
            r"git clone https://{username}@github.com/sweepai-dev/test"


# Class for ShellMessage
class ShellMessage(BaseModel):
    message: str
    error: bool = False


class Sandbox(BaseModel):
    token: str
    image: str = "Python3"
    session: Session

    @classmethod
    async def from_token(cls: Type[Self], token: str, **kwargs) -> Self:
        image = kwargs.get("image", "Python3")
        session = Session(image)
        await session.open()
        return cls(
            token=token,
            image=image,
            session=session
        )

    async def run_command(self, command: str):
        outputs = []
        proc = await self.session.process.start(
            cmd=command,
            on_stdout=lambda m: outputs.append(ShellMessage(message=m['line'])),
            on_stderr=lambda e: outputs.append(ShellMessage(message=e['line'], error=True)),
            on_exit=lambda: print("Exit"),
            rootdir="/code",
        )
        # await proc.send_stdin("token\n")
        # await proc.kill()
        await proc.finished
        await asyncio.sleep(0.05)  # Small delay to allow the process to finish
        return outputs

    async def clone_repo(self):
        raise NotImplementedError
