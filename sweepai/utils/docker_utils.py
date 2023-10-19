import requests
from datetime import datetime, timezone 

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
    response = requests.get(url)
    data = response.json()
    
    last_updated = datetime.fromisoformat(
        data["results"][0]["last_updated"]
    )
    duration_since_last_update = (
        datetime.now(timezone.utc) - last_updated
    )
    
    return humanize_time(duration_since_last_update)
