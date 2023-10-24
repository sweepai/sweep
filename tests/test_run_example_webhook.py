import json
import time

import requests

host = "http://0.0.0.0:8080"


def wait_for_server(host: str) -> None:
    for i in range(120):
        try:
            response = requests.get(host)
            if response.status_code == 200:
                break
        except:
            print(
                f"Waited for server to start ({i+1}s)"
                + ("." * (i % 4) + " " * (4 - (i % 4))),
                end="\r",
            )
            time.sleep(1)
            continue
    if i > 0:
        print(f"Waited for server to start ({i+1}s)")


if __name__ == "__main__":
    wait_for_server(host)
    with open("tests/jsons/check_suite_webhook.json", "r") as file:
        response = requests.post(
            host,
            json=json.load(file),
            headers={"X-GitHub-Event": "check_run"},
        )
    print(response)
