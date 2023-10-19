import requests


def get_latest_docker_version():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()
    return datetime.datetime.fromisoformat(data["results"][0]["last_updated"].rstrip('Z'))
