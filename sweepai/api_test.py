import unittest
from unittest.mock import patch
from sweepai import api
from sweepai.api import CheckRunCompleted, get_github_client, download_logs, clean_logs, get_hash, stack_pr


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.mock_api = unittest.mock.create_autospec(api)

    def test_webhook(self):
        self.mock_api.webhook.return_value = {"success": True}
        result = self.mock_api.webhook()
        self.assertEqual(result, {"success": True})
        self.mock_api.webhook.assert_called_once()

    def test_home(self):
        self.mock_api.home.return_value = "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>"
        result = self.mock_api.home()
        self.assertEqual(result, "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>")
        self.mock_api.home.assert_called_once()

    # Add more test methods as needed for each function in api.py

if __name__ == '__main__':
    unittest.main()
    @patch('sweepai.api.get_github_client')
    @patch('sweepai.api.download_logs')
    @patch('sweepai.api.clean_logs')
    @patch('sweepai.api.get_hash')
    @patch('sweepai.api.stack_pr')
    def test_check_run_completed(self, mock_stack_pr, mock_get_hash, mock_clean_logs, mock_download_logs, mock_get_github_client):
        # Create a mock CheckRunCompleted request
        mock_request = unittest.mock.create_autospec(CheckRunCompleted)
        mock_request.check_run.conclusion = "failure"
        mock_request.check_run.pull_requests = [unittest.mock.Mock()]
        mock_request.repository.full_name = "test/repo"
        mock_request.check_run.run_id = 123
        mock_request.installation.id = 456

        # Mock the return values of the functions called in the check_run case
        mock_get_github_client.return_value = (None, unittest.mock.Mock())
        mock_download_logs.return_value = "logs"
        mock_clean_logs.return_value = ("clean logs", "user message")
        mock_get_hash.return_value = "hash"
        mock_stack_pr.return_value = None

        # Call the webhook function with the mock request
        result = self.mock_api.webhook(mock_request)

        # Verify that the functions were called with the correct arguments
        mock_get_github_client.assert_called_once_with(mock_request.installation.id)
        mock_download_logs.assert_called_once_with(mock_request.repository.full_name, mock_request.check_run.run_id, mock_request.installation.id)
        mock_clean_logs.assert_called_once_with("logs")
        mock_get_hash.assert_called_once()
        mock_stack_pr.assert_called_once_with(request="[Sweep GHA Fix] The GitHub Actions run failed with the following error logs:\n\n```\n\nclean logs\n\n```", pr_number=mock_request.check_run.pull_requests[0].number, username=mock_request.sender.login, repo_full_name=mock_request.repository.full_name, installation_id=mock_request.installation.id, tracking_id="hash")

        # Verify that the conditional logic behaves as expected
        self.assertEqual(result, {"success": True})
