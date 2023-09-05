import os
from celery import Celery
from loguru import logger
from sweepai.config.server import REDIS_URL

# Create the Celery app with the constructed URLs
celery_app = Celery(
    "api",
    broker=REDIS_URL + '?ssl_cert_reqs=CERT_NONE',
    backend=REDIS_URL + '?ssl_cert_reqs=CERT_NONE',
    include=['sweepai.api']
)