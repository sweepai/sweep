from datetime import datetime, timedelta

import requests


def get_latest_docker_version():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()
    last_updated = datetime.strptime(
        data["results"][0]["last_updated"], "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    now = datetime.utcnow()
    diff = now - last_updated

    if diff < timedelta(minutes=1):
        return "just now"
    elif diff < timedelta(hours=1):
        return f"{diff.seconds // 60} minutes ago"
    elif diff < timedelta(days=1):
        return f"{diff.seconds // 3600} hours ago"
    else:
        return f"{diff.days} days ago"
