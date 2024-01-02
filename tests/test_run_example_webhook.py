import json

from fastapi.testclient import TestClient

from sweepai.api import app

if __name__ == "__main__":
    client = TestClient(app)
    response = client.post(
        "/",
        json=json.load(open("tests/jsons/opened_pull.json", "r")),
        headers={"X-GitHub-Event": "pull_request"},
    )
    print(response)
