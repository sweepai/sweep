import os
import sys

from fastapi import FastAPI
from starlette.responses import JSONResponse

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": sys.argv[-1]}


@app.get("/health")
def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "UP", "port": sys.argv[-1] if len(sys.argv) > 0 else -1},
    )
