from datetime import datetime, timezone

import requests


def get_latest_docker_version():
    url = "https://hub.docker.com/v2/namespaces/sweepai/repositories/sweep/tags"
    response = requests.get(url)
    data = response.json()
    last_updated = data["results"][0]["last_updated"]

    # Convert the date from string to datetime object
    last_updated_date = datetime.strptime(last_updated, "%Y-%m-%dT%H:%M:%S.%fZ")

    # Calculate the difference between the current date and the date of the last update
    time_diff = datetime.now(timezone.utc) - last_updated_date

    # Format the difference in a human-readable format
    if time_diff.days > 0:
        return f"{time_diff.days} days ago"
    elif time_diff.seconds // 3600 > 0:
        return f"{time_diff.seconds // 3600} hours ago"
    elif time_diff.seconds // 60 > 0:
        return f"{time_diff.seconds // 60} minutes ago"
    else:
        return "Just now"
