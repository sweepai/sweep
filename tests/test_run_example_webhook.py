import json

from fastapi.testclient import TestClient

from sweepai.api import app

if __name__ == "__main__":
    client = TestClient(app)
    response = client.post(
        "/",
        json=json.load(open("tests/jsons/sweep_rules_webhook.json", "r")),
        headers={"X-GitHub-Event": "push"},
    )
    print(response)
