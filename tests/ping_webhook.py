import json
import time

import requests

if __name__ == "__main__":
    for i in range(10):
        start_time = time.time()
        print(f"Sending {i}th attempt")
        response = requests.post(
            # "http://127.0.0.1:8080",
            "https://sweep-prod.ngrok.dev",
            json=json.load(open("tests/jsons/opened_pull.json", "r")),
            headers={"X-GitHub-Event": "test"},
        )
        print(f"Completed in {time.time() - start_time}s")
        print(response)
        print(response.text)
