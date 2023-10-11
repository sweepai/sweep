import logging as logger

import redis
from fastapi import FastAPI

from sweepai.config.server import REDIS_URL


def check_redis_health() -> str:
    """
    Check the health of the Redis server.

    Returns:
        str: "UP" if the Redis server is up, "DOWN" otherwise.
    """
    try:
        redis_client = redis.Redis.from_url(REDIS_URL)
        redis_client.ping()  # Ping the Redis server
        return "UP"
    except Exception as e:
        logger.exception(f"Redis health check failed: {e}")
        return "DOWN"


app = FastAPI()


@app.get("/health")
def health_check() -> str:
    """
    Endpoint for checking the health of the Redis server.

    Returns:
        str: "UP" if the Redis server is up, "DOWN" otherwise.
    """
    return check_redis_health()
