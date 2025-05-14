import urllib
from datetime import datetime, timedelta, timezone

import requests


def get_latest_docker_version():
    def humanize_time(delta):
        seconds = delta.total_seconds()
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days > 0:
            return f"{int(days)} days ago"
        elif hours > 0:
            return f"{int(hours)} hours ago"
        elif minutes > 0:
            return f"{int(minutes)} minutes ago"
        else:
            return "just now"

    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    try:
        response = requests.get(url, timeout=(1, 1))
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx and 5xx)
        data = response.json()
        truncated_time = data["results"][0]["last_updated"].split(".")[0]
        last_updated = datetime.fromisoformat(f"{truncated_time}+00:00")
    except Exception:
        # subtract 6 hours
        last_updated = datetime.now(timezone.utc) - timedelta(hours=6)
    # Truncate fractional seconds
    duration_since_last_update = datetime.now(timezone.utc) - last_updated
    return humanize_time(duration_since_last_update)


def get_docker_badge():
    try:
        docker_update_duration = get_latest_docker_version()
        encoded_duration = urllib.parse.quote(docker_update_duration)
        badge_url = f"https://img.shields.io/badge/Docker%20Version%20Updated-{encoded_duration}-blue"
        markdown_badge = f"<br/>![Docker Version Updated]({badge_url})"
        return markdown_badge
    except Exception:
        return ""
