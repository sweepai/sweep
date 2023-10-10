import psutil
from fastapi.responses import JSONResponse
from sweepai.config.server import IS_SELF_HOSTED

def check_sandbox_health():
    try:
        requests.get(os.path.join(SANDBOX_URL, "health"))
        return "UP"
    except Exception as e:
        logger.error(e)
        return "DOWN"


def check_mongodb_health():
    try:
        client = MongoClient(MONGODB_URI)
        client.server_info()  # Attempt to fetch server information
        return "UP"
    except Exception as e:
        logger.error(e)
        return "DOWN"


def check_redis_health():
    try:
        redis_client = redis.Redis.from_url(REDIS_URL)
        redis_client.ping()  # Ping the Redis server
        return "UP"
    except Exception as e:
        logger.error(e)
        return "DOWN"


def health_check():
    sandbox_status = check_sandbox_health()
    mongo_status = check_mongodb_health() if not IS_SELF_HOSTED else None
    redis_status = check_redis_health()

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
