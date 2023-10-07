"""Module to get the latest Docker version of SweepAI."""

import logging
import traceback

import requests


def get_latest_docker_version():
    """Get the latest Docker version of SweepAI from Docker Hub."""
    try:
        docker_url = "https://hub.docker.com/r/sweepai/sweep"
        response = requests.get(docker_url, timeout=10)
        response_json = response.json()
        latest_version = response_json["results"][0]["name"]
        return latest_version
    except requests.exceptions.RequestException as error:
        logging.error("An error occurred: %s\n%s", error, traceback.format_exc())
        return None
