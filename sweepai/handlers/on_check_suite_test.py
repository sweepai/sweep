import unittest
from unittest.mock import Mock, patch

from sweepai.handlers.on_check_suite import clean_logs, download_logs, on_check_suite


class TestOnCheckSuite(unittest.TestCase):
    @patch("requests.get")
    def test_download_logs(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"PK\x03\x04..."
        mock_get.return_value = mock_response

        logs = download_logs("test/repo", 123, 456)

        self.assertEqual(logs, "##[error] Test logs")

    def test_clean_logs(self):
        logs = "##[group] Test command ##[endgroup] Test logs ##[error] Test error"

        cleaned_logs, user_message = clean_logs(logs)

        self.assertEqual(
            cleaned_logs,
            "The command:\nTest command\nyielded the following error:\nTest error\n\nHere are the logs:\nTest logs",
        )
        self.assertEqual(
            user_message,
            "The command:\n`Test command`\nyielded the following error:\n`Test error`\nHere are the logs:\n```\nTest logs\n```",
        )

    @patch("sweepai.handlers.on_check_suite.get_github_client")
    @patch("sweepai.handlers.on_check_suite.get_gha_enabled")
    def test_on_check_suite(self, mock_get_gha_enabled, mock_get_github_client):
        mock_request = Mock()
        mock_request.check_run.pull_requests = [Mock()]
        mock_request.repository.full_name = "test/repo"
        mock_request.installation.id = 123
        mock_get_gha_enabled.return_value = True
        mock_get_github_client.return_value = (None, Mock())

        pr_change_request = on_check_suite(mock_request)

        self.assertEqual(pr_change_request.params["type"], "github_action")
        self.assertEqual(pr_change_request.params["repo_full_name"], "test/repo")
        self.assertEqual(pr_change_request.params["installation_id"], 123)
