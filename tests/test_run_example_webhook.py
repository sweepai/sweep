import json
import requests

response = requests.post(
    "http://127.0.0.1:8080",
    json=json.load(open("tests/example_webhook.json", "r")),
    headers={"X-GitHub-Event": "push"},
)
print(response)
