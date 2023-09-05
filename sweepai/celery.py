from celery import Celery
from loguru import logger
from redis import Redis, ConnectionError
from sweepai.config.server import REDIS_URL

try:
    # Attempt to connect using the provided REDIS_URL
    redis_client = Redis.from_url(REDIS_URL)
    response = redis_client.ping()
    if response:
        logger.info("Successfully connected to Redis.")
    else:
        raise ConnectionError
except ConnectionError:
    raise RuntimeError("Failed to establish Redis connection to both provided URL and localhost. \
                       Make sure Redis is running using docker run -p 6379:6379 -d redis and the URL was provided. Alternatively use `docker compose up --build`")

# Get host and port from the redis_client
redis_host = redis_client.connection_pool.connection_kwargs['host']
redis_port = redis_client.connection_pool.connection_kwargs['port']

# Construct URLs for broker and backend
broker_url = f"redis://{redis_host}:{redis_port}/0"
backend_url = f"redis://{redis_host}:{redis_port}/1"

# Create the Celery app with the constructed URLs
celery_app = Celery(
    "api",
    broker=broker_url,
    backend=backend_url,
    include=['sweepai.api']
)