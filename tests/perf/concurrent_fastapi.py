import hashlib
import threading
import time

from fastapi import FastAPI

from sweepai.utils.event_logger import logger

app = FastAPI()

with logger.contextualize(tracking_id="main"):
    logger.info(
        "Response code {code} HTTP/1.1 GET {url}",
        code=200,
        url="https://loki_handler.io",
    )


def get_hash():
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]


def worker_job(tracking_id: str = None):
    logger.bind(tracking_id=tracking_id)
    with logger.contextualize(tracking_id=tracking_id):
        logger.info(f"Start: inside the with statement from worker {tracking_id}")
        time.sleep(3)
        logger.info(f"End: inside the with statement from worker {tracking_id}")
    logger.info("Outside the with statement")


@app.post("/start_job/")
async def start_job():
    with logger.contextualize(tracking_id="main"):
        logger.info("Starting job")
        thread = threading.Thread(target=worker_job, args=(get_hash(),))
        thread.start()
        return {"message": "Job started"}
