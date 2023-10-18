import psutil
import redis
import requests
import yaml 
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger
from pymongo import MongoClient

from sweepai.config.server import IS_SELF_HOSTED, MONGODB_URI, REDIS_URL, SANDBOX_URL

app = FastAPI()


def check_sandbox_health() -> str:
    try:
        response = requests.get(SANDBOX_URL)
        response.raise_for_status()
        return "UP"
    except Exception as e:
        logger.exception(f"Error checking sandbox health: {e}")
        return "DOWN"


def check_mongodb_health() -> str:
    try:
        client = MongoClient(MONGODB_URI)
        client.admin.command("ismaster")
        return "UP"
    except Exception as e:
        logger.exception(f"Error checking MongoDB health: {e}")
        return "DOWN"


def check_redis_health() -> str:
    try:
        redis_client = redis.Redis.from_url(REDIS_URL)
        redis_client.ping()
        return "UP"
    except Exception as e:
        logger.exception(f"Error checking Redis health: {e}")
        return "DOWN"


def check_yaml_health() -> str: 
    try:
        with open("sweep.yaml", "r") as file:
            config = yaml.safe_load(file)
        return "UP"
    except yaml.YAMLError as e:
        logger.exception(f"Error checking YAML health: {e}")
        return "DOWN"

@app.get("/health")
def health_check():
    sandbox_status = check_sandbox_health()
    mongo_status = check_mongodb_health() if not IS_SELF_HOSTED else None
    redis_status = check_redis_health()
    yaml_status = check_yaml_health() 

    cpu_usage = psutil.cpu_percent(interval=0.1)
    memory_info = psutil.virtual_memory()
    disk_usage = psutil.disk_usage("/")
    network_traffic = psutil.net_io_counters()

    status = {
        "status": "UP",
        "details": {
            "sandbox": {
                "status": sandbox_status,
            },
            "mongodb": {
                "status": mongo_status,
            },
            "redis": {
                "status": redis_status,
            },
            "yaml": {
                "status": yaml_status,
            },
            "system_resources": {
                "cpu_usage": cpu_usage,
                "memory_usage": memory_info.used,
                "disk_usage": disk_usage.used,
                "network_traffic": {
                    "bytes_sent": network_traffic.bytes_sent,
                    "bytes_received": network_traffic.bytes_recv,
                },
            },
        },
    }

    return JSONResponse(status_code=200, content=status)
