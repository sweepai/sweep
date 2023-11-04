import pytest
from unittest.mock import Mock
from sweepai.api import webhook

def test_webhook_pull_request_created_more_than_an_hour_ago():
    request = Mock()
    request.headers.get.return_value = "check_run"
    request.json.return_value = {
        "action": "completed",
        "check_run": {
            "pull_requests": [
                {
                    "number": 1,
                    "created_at": "2022-01-01T00:00:00Z"
                }
            ]
        },
        "installation": {
            "id": 1
        },
        "repository": {
            "full_name": "test/test"
        }
    }
    assert webhook(request) is None

def test_webhook_pull_request_title_starts_with_sweep_rules():
    request = Mock()
    request.headers.get.return_value = "check_run"
    request.json.return_value = {
        "action": "completed",
        "check_run": {
            "pull_requests": [
                {
                    "number": 1,
                    "created_at": "2022-01-01T00:00:00Z",
                    "title": "[Sweep Rules] Test"
                }
            ]
        },
        "installation": {
            "id": 1
        },
        "repository": {
            "full_name": "test/test"
        }
    }
    assert webhook(request) is None

def test_webhook_pull_request_has_failed_check_suites():
    request = Mock()
    request.headers.get.return_value = "check_run"
    request.json.return_value = {
        "action": "completed",
        "check_run": {
            "pull_requests": [
                {
                    "number": 1,
                    "created_at": "2022-01-01T00:00:00Z",
                    "title": "[Sweep Rules] Test"
                }
            ],
            "conclusion": "failure"
        },
        "installation": {
            "id": 1
        },
        "repository": {
            "full_name": "test/test"
        }
    }
    assert webhook(request) is None

def test_webhook_pull_request_is_closed():
    request = Mock()
    request.headers.get.return_value = "pull_request"
    request.json.return_value = {
        "action": "closed",
        "pull_request": {
            "number": 1,
            "created_at": "2022-01-01T00:00:00Z",
            "title": "[Sweep Rules] Test"
        },
        "installation": {
            "id": 1
        },
        "repository": {
            "full_name": "test/test"
        }
    }
    assert webhook(request) is None
