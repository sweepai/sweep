import json
import time

import requests

if __name__ == "__main__":
    start_time = time.time()
    response = requests.post(
        "http://127.0.0.1:8080",
        json=json.load(open("tests/jsons/opened_pull.json", "r")),
        headers={"X-GitHub-Event": "test"},
    )
    print(f"Completed in {time.time() - start_time}s")
    print(response)
    print(response.text)
