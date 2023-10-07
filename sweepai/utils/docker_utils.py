import requests

def get_latest_docker_version():
    response = requests.get('https://registry.hub.docker.com/v1/repositories/sweepai/sweep/tags')
    tags = response.json()
    latest_version = tags[0]['name']
    return latest_version
