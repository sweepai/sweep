import requests
import docker
import pybadges

def get_dockerhub_version():
    response = requests.get("https://registry.hub.docker.com/v2/repositories/sweepai/sweep/tags/latest")
    data = response.json()
    version = data['name']
    return version

def get_current_docker_version():
    client = docker.from_env()
    version = client.version()["Version"]
    return version

def generate_badge(version1, version2):
    if version1 == version2:
        badge = pybadges.badge(left_text='Docker version', right_text='Up-to-date', right_color='green')
    else:
        badge = pybadges.badge(left_text='Docker version', right_text='Outdated', right_color='red')
    return badge

if __name__ == "__main__":
    dockerhub_version = get_dockerhub_version()
    current_version = get_current_docker_version()
    badge = generate_badge(dockerhub_version, current_version)
    print(badge)
