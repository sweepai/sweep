import hashlib
import time

from loguru import logger


def get_hash():
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]


if __name__ == "__main__":
    tracking_id = get_hash()
    logger.bind(tracking_id=tracking_id)
    with logger.contextualize(tracking_id=tracking_id):
        logger.info(f"Start: inside the with statement from worker {tracking_id}")
        for i in range(100000):
            logger.info(f"Inside the with statement from worker {tracking_id} (i={i})")
            time.sleep(1)
    logger.info("Outside the with statement")
