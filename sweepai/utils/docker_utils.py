import requests


def get_latest_docker_version():
    response = requests.get(
        "https://hub.docker.com/v2/repositories/sweepai/sweep/tags/"
    )
    response_json = response.json()
    latest_version = response_json["results"][0]["name"]
    return latest_version
