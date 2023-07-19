import redis
import logging

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self, redis_url):
        try:
            self.redis_instance = redis.from_url(redis_url)
            logger.info("Successfully connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_instance = None

    def get_data(self, key):
        try:
            return self.redis_instance.get(key)
        except Exception as e:
            logger.error(f"Failed to get data from Redis: {e}")
            return None

    def set_data(self, key, value):
        try:
            self.redis_instance.set(key, value)
        except Exception as e:
            logger.error(f"Failed to set data in Redis: {e}")

    def close_connection(self):
        try:
            self.redis_instance.close()
            logger.info("Successfully closed the connection to Redis")
        except Exception as e:
            logger.error(f"Failed to close the connection to Redis: {e}")