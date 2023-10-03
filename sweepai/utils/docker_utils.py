from datetime import datetime
import requests
import json
import subprocess

def get_docker_hub_version():
    response = requests.get('https://hub.docker.com/v2/repositories/sweepai/sweep/tags')
    data = json.loads(response.text)
    for result in data['results']:
        last_pushed = result['images'][0]['last_pushed']
        if last_pushed:
            return last_pushed
    return 'No version found'

def get_local_docker_version():
    result = subprocess.run(['docker', 'images', 'sweepai/sweep', '--format', '{{.CreatedAt}}'], stdout=subprocess.PIPE)
    version = result.stdout.decode('utf-8').strip()
    version = version.splitlines()[0]
    return version if version else 'No version found'


def get_docker_version_badge():
    try:
        hub_version = get_docker_hub_version()
        local_version = get_local_docker_version()
        docker_hub_time = datetime.fromisoformat(hub_version.replace("Z", "+00:00"))
        local_docker_time = datetime.strptime(local_version, '%Y-%m-%d %H:%M:%S %z %Z')
        # Calculating the time delta
        time_delta = docker_hub_time - local_docker_time
        if time_delta.total_seconds() < 10:
            return 'https://img.shields.io/badge/Docker_Version-Up_to_date-blue'
        else:
            return 'https://img.shields.io/badge/Docker_Version-Outdated-red'
    except Exception:
        return None