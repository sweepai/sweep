import json

from fastapi.testclient import TestClient

from sweepai.api import app

if __name__ == "__main__":
    client = TestClient(app)
    response = client.post(
        "/",
        json=json.load(open("tests/jsons/failed_check_run.json", "r")),
        headers={"X-GitHub-Event": "check_run"},
    )
    print(response)
