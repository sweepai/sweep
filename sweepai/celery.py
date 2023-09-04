from celery import Celery
from loguru import logger
from redis import Redis
from celery.contrib.abortable import AbortableTask

redis_client = Redis(host='redis', port=6379, db=2)

celery_app = Celery(
    "api",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/1",
    include=['sweepai.api']
)