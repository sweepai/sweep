import requests

def get_latest_docker_version():
    response = requests.get('https://hub.docker.com/r/sweepai/sweep/tags?page=1&page_size=25')
    data = response.json()
    latest_version = data['results'][0]['name']
    return latest_version
