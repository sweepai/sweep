import requests
import json

def get_latest_docker_version():
    response = requests.get('https://hub.docker.com/r/sweepai/sweep')
    response_json = json.loads(response.text)
    latest_version = response_json['results'][0]['last_pushed']
    return latest_version
