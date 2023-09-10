import os
from celery import Celery
from loguru import logger
from sweepai.config.server import REDIS_URL
from ssl import CERT_NONE

celery_app = Celery("api", broker=REDIS_URL, backend=REDIS_URL, include=["sweepai.api"])
