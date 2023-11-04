import unittest
from unittest.mock import Mock, patch

from sweepai.api import webhook


class TestWebhook(unittest.TestCase):
    @patch("sweepai.handlers.on_pr_commit.handle_pr_commit")
    def test_handle_pr_commit_called_on_pr_opened_or_synchronize(
        self, mock_handle_pr_commit
    ):
        # Create a mock request simulating a "pull_request" event with "opened" action
        mock_request = Mock()
        mock_request.headers = {"X-GitHub-Event": "pull_request"}
        mock_request.json = {"action": "opened"}

        # Call the webhook function with the mock request
        webhook(mock_request)

        # Assert that the handle_pr_commit function was called
        mock_handle_pr_commit.assert_called_once()

        # Reset the mock
        mock_handle_pr_commit.reset_mock()

        # Create a mock request simulating a "pull_request" event with "synchronize" action
        mock_request.json = {"action": "synchronize"}

        # Call the webhook function with the mock request
        webhook(mock_request)

        # Assert that the handle_pr_commit function was called
        mock_handle_pr_commit.assert_called_once()
