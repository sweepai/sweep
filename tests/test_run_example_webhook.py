import json
import requests

response = requests.post(
    "http://147.182.237.149:8000",
    json=json.load(open("tests/example_webhook.json", "r")),
    headers={"X-GitHub-Event": "issues"},
)
print(response)
