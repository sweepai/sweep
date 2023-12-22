import pytest
from fastapi.testclient import TestClient

from sweepai.api import app, handle_gitlab_webhook, webhook_redirect

client = TestClient(app)

# Test data mimicking GitLab issue webhook payload
test_data_issue_open = {
    "object_kind": "issue",
    "event_type": "issue",
    "object_attributes": {
        "action": "open",
        "title": "Test issue",
        "id": 1,
        "url": "https://gitlab.com/test/test/-/issues/1",
    },
    "labels": [{"id": 1, "title": "test", "color": "#ffffff", "description": "test"}],
}

# Test data mimicking GitLab issue webhook payload for update action
test_data_issue_update = {
    "object_kind": "issue",
    "event_type": "issue",
    "object_attributes": {
        "action": "update",
        "title": "Test issue",
        "id": 1,
        "url": "https://gitlab.com/test/test/-/issues/1",
    },
    "labels": [{"id": 1, "title": "test", "color": "#ffffff", "description": "test"}],
}

def test_webhook_redirect():
    response = client.post("/webhook", json=test_data_issue_open, headers={"X-GitLab-Event": "Issue Hook"})
    assert response.status_code == 200
    assert response.json() == {"status": "GitLab issue webhook processed successfully"}

    response = client.post("/webhook", json=test_data_issue_update, headers={"X-GitLab-Event": "Issue Hook"})
    assert response.status_code == 200
    assert response.json() == {"status": "GitLab issue webhook processed successfully"}

    response = client.post("/webhook", json=test_data_issue_open)
    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported GitLab event"}

def test_handle_gitlab_webhook():
    response = client.post("/webhook/gitlab/issue", json=test_data_issue_open)
    assert response.status_code == 200
    assert response.json() == {"status": "GitLab issue webhook processed successfully"}

    response = client.post("/webhook/gitlab/issue", json=test_data_issue_update)
    assert response.status_code == 200
    assert response.json() == {"status": "GitLab issue webhook processed successfully"}

    test_data_issue_invalid = test_data_issue_open.copy()
    test_data_issue_invalid["object_attributes"]["action"] = "invalid"
    response = client.post("/webhook/gitlab/issue", json=test_data_issue_invalid)
    assert response.status_code == 400
    assert response.json() == {"detail": "Unsupported GitLab event"}
