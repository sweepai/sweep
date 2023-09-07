import json
import requests
import time

port = "http://0.0.0.0:8080"
# port = "http://127.0.0.1:8080"

response = requests.post(
    port,
    json=json.load(open("tests/issue_webhook.json", "r")),
    headers={"X-GitHub-Event": "issues"},
)
print(response)