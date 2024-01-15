import subprocess

from fastapi import FastAPI
from loguru import logger

app = FastAPI()


@app.post("/start_job/")
async def start_job():
    with logger.contextualize(tracking_id="main"):
        logger.info("Starting job")
        subprocess.Popen(["python", "worker.py"])
        return {"message": "Job started"}
