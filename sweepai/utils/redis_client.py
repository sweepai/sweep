import time

import redis
import docker


class RedisClient:
    def __init__(self, url: str | None = None):
        if url:
            self.client = redis.Redis.from_url(url)
        self.client = None
        # else:
        #     self.client = redis.Redis(host="localhost", port=6379, db=0)
        #     for _ in range(5):
        #         try:
        #             print("Trying to connect to Redis...")
        #             self.client.ping()
        #             break
        #         except redis.exceptions.ConnectionError as e:
        #             print(e)
        #             print("Redis not running, starting...")
        #             RedisClient.start_local()
        #             time.sleep(2)
        #     else:
        #         raise Exception("Could not connect to Redis.")
        #     print("Connected to Redis.")

    @staticmethod
    def start_local():
        client = docker.from_env()
        try:
            client.containers.get("redis")
            print("Redis already running.")
        except docker.errors.NotFound:
            print("Starting new Redis container.")
            client.containers.run(
                "redis", detach=True, ports={"6379/tcp": 6379}, name="redis"
            )

    @staticmethod
    def stop_local():
        client = docker.from_env()
        container = client.containers.get("redis")
        container.stop()
        container.remove()
