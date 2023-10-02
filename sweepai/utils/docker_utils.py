import requests
import json
import subprocess

def get_docker_hub_version():
    response = requests.get('https://hub.docker.com/v2/repositories/sweepai/sweep/tags')
    data = json.loads(response.text)
    version = data['results'][0]['name']
    return version

def get_local_docker_version():
    result = subprocess.run(['docker', 'images', 'sweepai/sweep', '--format', '{{.Tag}}'], stdout=subprocess.PIPE)
    version = result.stdout.decode('utf-8').strip()
    return version

def get_docker_version_badge():
    try:
        hub_version = get_docker_hub_version()
        local_version = get_local_docker_version()
        if hub_version == local_version:
            return 'Up-to-date'
        else:
            return 'Outdated'
    except Exception:
        return 'Error'
