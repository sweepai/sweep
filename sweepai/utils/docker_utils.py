from distutils.version import LooseVersion
import requests
import traceback

def get_latest_docker_version():
    try:
        response = requests.get("https://hub.docker.com/r/sweepai/sweep")
        response_json = response.json()
        versions = [result["name"] for result in response_json["results"]]
        latest_version = str(max(LooseVersion(version) for version in versions))
        return latest_version
    except Exception as e:
        traceback.print_exc()
        raise e
