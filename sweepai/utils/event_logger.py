import json

import requests
from loguru import logger
from posthog import Posthog

from sweepai.config.server import ENV, LOKI_URL, POSTHOG_API_KEY

if POSTHOG_API_KEY is None or POSTHOG_API_KEY.lower() == "none":
    posthog = Posthog(
        project_api_key="none", disabled=True, host="https://app.posthog.com"
    )
    logger.warning(
        "Initialized an empty Posthog instance as POSTHOG_API_KEY is not present."
    )
else:
    posthog = Posthog(project_api_key=POSTHOG_API_KEY, host="https://app.posthog.com")


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
