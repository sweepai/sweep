"""Module to get the latest Docker version of the SweepAI application."""

import requests


def get_latest_docker_version():
    """Function to get the latest Docker version of the SweepAI application."""
    response = requests.get(
        "https://registry.hub.docker.com/v2/repositories/sweepai/sweep/tags/", timeout=5
    )
    response_dict = response.json()
    latest_version = response_dict["results"][0]["name"]
    return latest_version
