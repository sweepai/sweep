import json
import time

import requests

host = "http://localhost:8080"


def wait_for_server(host: str, max_attempts: int = 120) -> None:
    for i in range(max_attempts):
        try:
            response = requests.get(host)
            if response.status_code == 200:
                print(f"Server started after {i+1}s")
                break
        except requests.exceptions.ConnectionError:
            if i < max_attempts - 1:  # Don't sleep on the last iteration
                print(
                    f"Server not up, retrying in 1s ({i+1}/{max_attempts})"
                    + ("." * (i % 4) + " " * (4 - (i % 4))),
                    end="\r",
                )
                time.sleep(1)
            else:
                raise Exception("Server did not start after maximum number of attempts")


if __name__ == "__main__":
    wait_for_server(host)
    with open("tests/jsons/check_suite_webhook.json", "r") as file:
        response = requests.post(
            host,
            json=json.load(file),
            headers={"X-GitHub-Event": "check_run"},
        )
    print(response)
