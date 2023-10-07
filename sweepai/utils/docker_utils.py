"""Module to get the latest Docker version from Docker Hub."""

import json
import os

import requests


def get_latest_docker_version():
    """Get the latest Docker version from Docker Hub."""
    username = os.getenv("DOCKER_HUB_USERNAME")
    password = os.getenv("DOCKER_HUB_PASSWORD")

    session = requests.Session()
    session.auth = (username, password)

    url = "https://hub.docker.com/r/sweepai/sweep"
    response = session.get(url)
    response_content = json.loads(response.content)
    latest_version = response_content["results"][0]["name"]
    return latest_version
