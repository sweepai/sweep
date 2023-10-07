import requests
import logging

logger = logging.getLogger(__name__)

def get_latest_docker_version():
    try:
        response = requests.get('https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags')
        data = response.json()
        last_updated = data['results'][0]['last_updated']
        return last_updated
    except Exception:
        logger.exception("Error getting latest Docker version")
        return None
