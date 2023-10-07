import requests

def get_latest_docker_version():
    response = requests.get('https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags')
    data = response.json()
    last_updated = data['results'][0]['last_updated']
    return last_updated
