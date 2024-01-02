import hashlib
import threading
import time

from fastapi import FastAPI
from loguru import logger

app = FastAPI()


def get_hash():
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]


def custom_sink(message):
    print(message.record["extra"])  # Print the context


def worker_job(tracking_id: str = None):
    logger.add(custom_sink)
    logger.bind(tracking_id=tracking_id)
    with logger.contextualize(
        # metadata={
        #     "tracking_id": tracking_id,
        # }
        tracking_id=tracking_id
    ):
        print("Job completed after 5 seconds")
        logger.info("Inside the with statement")
    logger.info("Outside the with statement")


@app.post("/start_job/")
async def start_job():
    thread = threading.Thread(target=worker_job, args=(get_hash(),))
    thread.start()
    return {"message": "Job started"}
