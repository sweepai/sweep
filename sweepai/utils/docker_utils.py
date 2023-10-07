import requests

def get_latest_docker_version_date():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()

    for item in data['results']:
        if item['name'] == 'latest':
            return item['last_updated']

    return None
