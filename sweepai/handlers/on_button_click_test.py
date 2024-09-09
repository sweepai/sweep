from unittest.mock import Mock, patch

from sweepai.handlers.on_button_click import handle_button_click


def test_handle_button_click():
    mock_request_dict = {
        "installation": {"id": 1},
        "comment": {"body": "test body"},
        "repository": {"full_name": "test/repo"},
        "issue": {"number": 1},
    }

    with patch(
        "sweepai.handlers.on_button_click.get_github_client"
    ) as mock_get_github_client:
        mock_get_github_client.return_value = ("token", Mock())
        handle_button_click(mock_request_dict)


def test_handle_button_click_revert_files():
    mock_request_dict = {
        "installation": {"id": 1},
        "comment": {"body": "test body"},
        "repository": {"full_name": "test/repo"},
        "issue": {"number": 1},
        "changes": {"title": "REVERT_CHANGED_FILES_TITLE"},
    }

    with patch(
        "sweepai.handlers.on_button_click.get_github_client"
    ) as mock_get_github_client:
        mock_get_github_client.return_value = ("token", Mock())
        handle_button_click(mock_request_dict)


def test_handle_button_click_rules():
    mock_request_dict = {
        "installation": {"id": 1},
        "comment": {"body": "test body"},
        "repository": {"full_name": "test/repo"},
        "issue": {"number": 1},
        "changes": {"title": "RULES_TITLE"},
    }

    with patch(
        "sweepai.handlers.on_button_click.get_github_client"
    ) as mock_get_github_client:
        mock_get_github_client.return_value = ("token", Mock())
        handle_button_click(mock_request_dict)
