import json
import requests

response = requests.post(
    "http://127.0.0.1:8000/webhook",
    json=json.load(open("tests/example_webhook.json", "r")),
    headers={"X-GitHub-Event": "issues"},
)
print(response)
