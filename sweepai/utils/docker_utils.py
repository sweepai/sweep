import requests


def get_latest_docker_version():
    url = "https://hub.docker.com/r/sweepai/sweep"
    response = requests.get(url)
    latest_version = response.json()["results"][0]["name"]
    return latest_version
