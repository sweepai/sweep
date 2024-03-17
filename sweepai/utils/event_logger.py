import json
from dataclasses import dataclass
from datetime import datetime  # Correctly import the datetime class

import requests
from loguru import logger
from pymongo import MongoClient

from sweepai.config.server import ENV, MONGODB_URI, POSTHOG_API_KEY

mongodb_client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=20000,
    socketTimeoutMS=20000,
)


@dataclass
class PosthogClient:
    """
    Official Posthog API client has a thread leakage, so we are using a custom client.
    """

    API_KEY: str | None = None

    def capture(
        self,
        distinct_id: str | None = None,
        event: str | None = None,
        properties: dict[str, str] | None = None,
        **kwargs,
    ):
        if self.API_KEY is None:
            return
        url = "https://app.posthog.com/capture/"
        headers = {"Content-Type": "application/json"}
        payload = {
            "api_key": self.API_KEY,
            "event": event,
            "properties": {"distinct_id": distinct_id, **properties},
            "timestamp": datetime.utcnow().isoformat()
            + "Z",  # Adding 'Z' to indicate UTC time
        }
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        return response


posthog = PosthogClient(API_KEY=POSTHOG_API_KEY)


def mongodb_sink(message):
    try:
        db = mongodb_client["llm"]
        collection = db["logs"]
        record = message.record
        log_data = {
            "time": record["time"].isoformat(),
            "file": {"name": record["file"].name, "path": record["file"].path},
            "thread": {"id": record["thread"].id, "name": record["thread"].name},
            "level": {
                "name": record["level"].name,
                "no": record["level"].no,
                "icon": record["level"].icon,
            },
            "process": {"id": record["process"].id, "name": record["process"].name},
            "tracking_id": record.get("tracking_id", ""),
        }
        for key in ["time", "level", "file", "thread", "process", "elapsed"]:
            if key in record:
                del record[key]
        log_data.update(record)
        return collection.insert_one(log_data)
    except Exception as e:
        print("Error sending log to MongoDB:", e)
        raise e


if MONGODB_URI:
    sink_id = logger.add(mongodb_sink)
    logger.bind(env=ENV)

if __name__ == "__main__":
    mongodb_client["llm"]["logs"].create_index("time")
    mongodb_client["llm"]["logs"].create_index("tracking_id")
    logger.info("Hello, World!")
    # fetch last five docs
    for doc in mongodb_client["llm"]["logs"].find().sort([("time", -1)]).limit(5):
        print(doc)
