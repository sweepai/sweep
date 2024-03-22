import json
import time

import requests

# if __name__ == "__main__":
#     for i in range(10):
#         start_time = time.time()
#         print(f"Sending {i}th attempt")
#         response = requests.post(
#             # "http://127.0.0.1:8080",
#             "https://sweep-prod.ngrok.dev",
#             json=json.load(open("tests/jsons/opened_pull.json", "r")),
#             headers={"X-GitHub-Event": "test"},
#         )
#         print(f"Completed in {time.time() - start_time}s")
#         print(response)
#         print(response.text)

import json
import time

import requests

if __name__ == "__main__":

    start_time = time.time()

    from fastapi.testclient import TestClient
    from sweepai.api import app
    def send_request(issue_request):
        with TestClient(app) as client:
            response = client.post(
                "/", json=issue_request, headers={"X-GitHub-Event": "pull_request"}
            )
            print(response)  # or return response, depending on your needs
    issue_request = json.loads(open("tests/jsons/pull_request_closed.json", "r").read())
    send_request(issue_request)
