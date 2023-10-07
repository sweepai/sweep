import requests
import json

def get_latest_docker_version():
    url = "https://hub.docker.com/r/sweepai/sweep"
    response = requests.get(url)
    response_content = json.loads(response.content)
    latest_version = response_content['results'][0]['name']
    return latest_version
