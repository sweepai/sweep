import requests
from requests.exceptions import RequestException


def get_latest_docker_version():
    url = "https://hub.docker.com/r/sweepai/sweep"
    try:
        response = requests.get(url)
        latest_version = response.json()["results"][0]["name"]
        return latest_version
    except RequestException:
        return None
