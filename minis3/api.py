from pathlib import Path
from threading import Lock

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()
storage_path = Path("public")
storage_path.mkdir(exist_ok=True)
lock = Lock()

app.mount("/public", StaticFiles(directory="public"), name="public")


class FilePayload(BaseModel):
    content: str
    filename: str


@app.post("/")
async def upload_svg(payload: FilePayload):
    with lock:
        dest = storage_path / payload.filename
        with dest.open("w") as buffer:
            buffer.write(payload.content)

    return {
        "url": f"/public/{payload.filename}",
        "filename": payload.filename,
    }
