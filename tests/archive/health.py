import json
import time

import requests

from sweepai.config.server import DISCORD_STATUS_WEBHOOK_URL


def log_discord(message):
    data = {"content": message}
    headers = {"Content-Type": "application/json"}
    response = requests.post(
        DISCORD_STATUS_WEBHOOK_URL, data=json.dumps(data), headers=headers
    )


def track_status(delay=5, failed_requests=6):
    counter = 0
    down = False

    # Every 10 seconds, check if the server is healthy. If it's not healthy 6 times in a row, then it's down.
    # Keep a counter based on health. If the down state updates, print it
    while True:
        time.sleep(delay)
        try:
            response = requests.get(DISCORD_STATUS_WEBHOOK_URL)
            if response.status_code != 200:
                healthy = False
            else:
                healthy = True
        except requests.exceptions.ConnectionError:
            healthy = False

        print(f"State: {healthy} ", end="\r")

        if not healthy:
            counter += 1
            if counter > failed_requests:
                counter = failed_requests
        else:
            counter -= 1
            if counter < 0:
                counter = 0

        prev_down = down
        if counter == failed_requests:
            down = True
        elif counter == 0:
            down = False

        if prev_down != down:
            if down:
                log_discord("Sweep is currently down.")
            else:
                log_discord("Sweep is now back up.")


track_status()
