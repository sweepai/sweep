import requests
from datetime import datetime, timezone

def get_latest_docker_version():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()
    last_updated = datetime.strptime(data["results"][0]["last_updated"], "%Y-%m-%dT%H:%M:%S.%fZ")
    now = datetime.now(timezone.utc)
    diff = now - last_updated
    if diff.days > 0:
        return f"{diff.days} days ago"
    else:
        hours = diff.seconds // 3600
        return f"{hours} hours ago"
