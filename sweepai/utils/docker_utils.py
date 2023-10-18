from datetime import datetime

import requests


def get_latest_docker_version():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()
    last_updated = datetime.strptime(
        data["results"][0]["last_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    duration = datetime.now() - last_updated
    return str(duration)
