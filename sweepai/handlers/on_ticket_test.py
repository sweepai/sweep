import unittest
from unittest.mock import Mock, patch

from sweepai.handlers.on_ticket import on_ticket


class TestOnTicket(unittest.TestCase):
    def setUp(self):
        self.issue = Mock()
        self.issue.title = "Test Issue"
        self.issue.summary = "This is a test issue"
        self.issue.issue_number = 1
        self.issue.issue_url = "https://github.com/test/repo/issues/1"
        self.issue.username = "testuser"
        self.issue.repo_full_name = "test/repo"
        self.issue.repo_description = "Test Repo"
        self.issue.installation_id = 12345
        self.issue.file_paths = ["file1.py", "file2.py"]
        self.issue.non_python_files = ["file3.txt", "file4.md"]

    @patch("sweepai.handlers.on_ticket.get_github_client")
    def test_on_ticket_with_exception(self, mock_get_github_client):
        mock_get_github_client.side_effect = Exception("Test exception")
        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
        )
        self.assertFalse(result["success"])

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.SweepBot.validate_file_change_requests")
    @patch("sweepai.handlers.on_ticket.SweepBot.generate_pull_request")
    @patch("sweepai.handlers.on_ticket.SweepBot.update_asset")
    @patch("sweepai.handlers.on_ticket.repo.get_issue")
    @patch("sweepai.handlers.on_ticket.create_pr_changes")
    def test_on_ticket_with_different_responses_2(self, mock_create_pr_changes, mock_get_issue, mock_update_asset, mock_generate_pull_request, mock_validate_file_change_requests, mock_get_github_client):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_validate_file_change_requests.return_value = Mock()
        mock_generate_pull_request.return_value = Mock()
        mock_update_asset.return_value = Mock()
        mock_get_issue.return_value = Mock()
        mock_create_pr_changes.return_value = Mock()
        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
            self.issue.file_paths,
            self.issue.non_python_files,
        )
        self.assertTrue(result["success"])
    def test_on_ticket(self, mock_get_github_client):
        mock_get_github_client.return_value = (Mock(), Mock())
        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
        )
        self.assertTrue(result["success"])

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change")
    @patch("sweepai.handlers.on_ticket.SweepBot.validate_sandbox")
    def test_on_ticket_with_different_responses(self, mock_validate_sandbox, mock_get_files_to_change, mock_get_github_client):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_get_files_to_change.return_value = (Mock(), Mock())
        mock_validate_sandbox.return_value = (Mock(), Mock())
        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
            self.issue.file_paths,
            self.issue.non_python_files,
        )
        self.assertTrue(result["success"])
    def test_on_ticket_with_exception(self, mock_get_github_client):
        mock_get_github_client.side_effect = Exception("Test exception")
        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
        )
        self.assertFalse(result["success"])

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.utils.ticket_utils.handle_payment_logic")
    def test_handle_payment_logic(
        self, mock_handle_payment_logic, mock_get_github_client
    ):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_handle_payment_logic.return_value = (True, True, False, Mock())

        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
        )

        mock_handle_payment_logic.assert_called_once_with(
            self.issue.repo_full_name,
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            None,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
            None,
            False,
            mock_get_github_client.return_value[1],
            False,
            False,
        )

        self.assertTrue(result["success"])

        mock_handle_payment_logic.return_value = (False, False, False, Mock())

        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
        )

        self.assertFalse(result["success"])
