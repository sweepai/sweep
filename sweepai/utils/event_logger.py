import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any  # Correctly import the datetime class

import requests
from loguru import logger

from sweepai.config.server import ENV, LOKI_URL, POSTHOG_API_KEY


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
        properties: dict[str, Any] | None = None,
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


def loki_sink(message):
    try:
        record = message.record

        extras = {
            **record["extra"],
            "level": record["level"].name,
            "file": record["file"].path,
            "line": record["line"],
        }

        message = (
            f"{record['time'].isoformat()} {record['level'].name}:{record['file'].path}:{record['line']}: {record['message']}\n\n"
            + json.dumps(extras)
        )

        log_data = {
            "streams": [
                {
                    "stream": {
                        "level": record["level"].name,
                        "env": ENV,
                        # "file": record["file"].path,
                        # "line": record["line"],
                    },
                    "values": [[str(int(record["time"].timestamp() * 1e9)), message]],
                }
            ]
        }

        for key, value in list(record["extra"].items())[:10]:
            if key in ["env"]:
                log_data["streams"][0]["stream"][key] = str(value)

        response = requests.post(
            LOKI_URL,
            data=json.dumps(log_data),
            headers={"Content-Type": "application/json"},
        )
        if response.status_code not in (200, 204):
            print("Error sending log to Loki:", response.text)
    except Exception as e:
        print("Error sending log to Loki:", e)


if LOKI_URL:
    sink_id = logger.add(loki_sink)
    logger.bind(env=ENV)
