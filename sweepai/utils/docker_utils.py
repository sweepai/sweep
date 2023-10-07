"""Module to get the latest Docker version of SweepAI."""

import requests


def get_latest_docker_version():
    """Get the latest Docker version of SweepAI from Docker Hub."""
    docker_url = "https://hub.docker.com/r/sweepai/sweep"
    response = requests.get(docker_url, timeout=10)
    response_json = response.json()
    latest_version = response_json["results"][0]["name"]
    return latest_version
