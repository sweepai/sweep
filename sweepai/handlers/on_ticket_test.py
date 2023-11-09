import unittest
from unittest.mock import Mock, patch

from sweepai.handlers.on_ticket import on_ticket, search_logic, create_pull_request_logic

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
        self.issue.comment_id = None
        self.issue.edited = False
        self.issue.tracking_id = None

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.search_logic")
    @patch("sweepai.handlers.on_ticket.create_pull_request_logic")
    def test_on_ticket(self, mock_get_github_client, mock_search_logic, mock_create_pull_request_logic):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_search_logic.return_value = True
        mock_create_pull_request_logic.return_value = True
        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
            self.issue.comment_id,
            self.issue.edited,
            self.issue.tracking_id,
        )
        self.assertTrue(result["success"])

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.search_logic")
    @patch("sweepai.handlers.on_ticket.create_pull_request_logic")
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
    @patch("sweepai.handlers.on_ticket.search_logic")
    @patch("sweepai.handlers.on_ticket.create_pull_request_logic")
    def test_on_ticket_with_exception(self, mock_get_github_client, mock_search_logic, mock_create_pull_request_logic):
        mock_get_github_client.side_effect = Exception("Test exception")
        mock_search_logic.return_value = True
        mock_create_pull_request_logic.return_value = True
        result = on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
            self.issue.comment_id,
            self.issue.edited,
            self.issue.tracking_id,
        )
        self.assertFalse(result["success"])

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.search_logic")
    @patch("sweepai.handlers.on_ticket.create_pull_request_logic")
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
    def test_search_logic(self, mock_get_github_client, mock_search_logic, mock_create_pull_request_logic):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_search_logic.return_value = True
        mock_create_pull_request_logic.return_value = True
        result = search_logic(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
            self.issue.comment_id,
            self.issue.edited,
            self.issue.tracking_id,
        )
        self.assertTrue(result["success"])

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.search_logic")
    @patch("sweepai.handlers.on_ticket.create_pull_request_logic")
    def test_create_pull_request_logic(self, mock_get_github_client, mock_search_logic, mock_create_pull_request_logic):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_search_logic.return_value = True
        mock_create_pull_request_logic.return_value = True
        result = create_pull_request_logic(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id,
            self.issue.comment_id,
            self.issue.edited,
            self.issue.tracking_id,
        )
        self.assertTrue(result["success"])
