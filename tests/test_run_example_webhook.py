import json

from fastapi.testclient import TestClient

from sweepai.api import app

if __name__ == "__main__":
    client = TestClient(app)
    response = client.post(
        "/",
        json=json.load(open("tests/jsons/issue_comment_edits.json", "r")),
        headers={"X-GitHub-Event": "issue_comment"},
    )
    print(response)
