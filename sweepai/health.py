from loguru import logger
import redis
from sweepai.config.server import REDIS_URL

def check_redis_health() -> str:
    try:
        redis_client = redis.Redis.from_url(REDIS_URL)
        redis_client.ping()  # Ping the Redis server
        return "UP"
    except Exception as e:
        logger.error(e)
        return "DOWN"
