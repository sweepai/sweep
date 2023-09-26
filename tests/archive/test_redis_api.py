import pickle
import time

import docker
import redis


class RedisClient:
    def __init__(self):
        self.client = redis.Redis(host="localhost", port=6379, db=0)
        for _ in range(10):
            try:
                print("Trying to connect to Redis...")
                self.client.ping()
                break
            except redis.exceptions.ConnectionError:
                print("Redis not running, starting...")
                RedisClient.start_local()
                time.sleep(1)
        else:
            raise Exception("Could not connect to Redis.")
        print("Connected to Redis.")

    def get(self, key):
        return pickle.loads(self.client.get(key))

    def set(self, key, value):
        self.client.set(pickle.dumps(key), pickle.dumps(value))

    def exists(self, key):
        return self.client.exists(key)

    @staticmethod
    def start_local():
        client = docker.from_env()
        client.containers.run(
            "redis", detach=True, ports={"6379/tcp": 6379}, name="redis"
        )

    @staticmethod
    def stop_local():
        client = docker.from_env()
        container = client.containers.get("redis")
        container.stop()
        container.remove()


redis_client = RedisClient()


def expensive_operation(name: str):
    print("Running operation...")
    time.sleep(5)
    return name


def cached_operation(name: str):
    if redis_client.exists(name):
        return redis_client.get(name)
    else:
        result = expensive_operation(name)
        redis_client.set(name, result)
        return result


if __name__ == "__main__":
    print(cached_operation("test"))
    print(cached_operation("test"))
