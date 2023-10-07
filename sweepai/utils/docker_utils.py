import requests


def get_latest_docker_version_date():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()
    latest_version_date = data["results"][0]["last_updated"]
    return latest_version_date
