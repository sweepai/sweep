import requests
import datetime
import humanize

def get_latest_docker_version():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()
    last_updated = datetime.datetime.fromisoformat(data["results"][0]["last_updated"].rstrip('Z'))
    duration_since_last_update = datetime.datetime.now(datetime.timezone.utc) - last_updated
    return humanize.naturaltime(duration_since_last_update)
