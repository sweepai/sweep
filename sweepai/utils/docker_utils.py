import requests


def get_latest_docker_version():
    url = "https://hub.docker.com/v2/repositories/sweepai/sweep/tags"
    response = requests.get(url)
    data = response.json()
    results = data["results"]
    sorted_results = sorted(results, key=lambda x: x["last_updated"], reverse=True)
    return sorted_results[0]["name"], sorted_results[0]["last_updated"]
