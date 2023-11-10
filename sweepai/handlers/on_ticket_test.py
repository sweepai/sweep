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

    @patch("sweepai.handlers.on_ticket.get_github_client")
    def test_on_ticket_with_exception(self, mock_get_github_client):
        with patch("sweepai.handlers.on_ticket.get_github_client") as mock_get_github_client:
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
            mock_get_github_client.assert_called_once()

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.get_github_client")
    def test_on_ticket_get_github_client_invalid_credentials(self, mock_get_github_client):
        with patch("sweepai.handlers.on_ticket.get_github_client") as mock_get_github_client:
            mock_get_github_client.side_effect = BadCredentialsException("Bad credentials")
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
            mock_get_github_client.assert_called_once()
    def test_on_ticket(self, mock_get_github_client):
        with patch("sweepai.handlers.on_ticket.fetch_relevant_files") as mock_fetch_relevant_files, \
             patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change") as mock_get_files_to_change, \
             patch("sweepai.handlers.on_ticket.SweepBot.generate_pull_request") as mock_generate_pull_request:
            mock_get_github_client.return_value = (Mock(), Mock())
            mock_fetch_relevant_files.return_value = (Mock(), Mock(), Mock())
            mock_get_files_to_change.return_value = [Mock()]
            mock_generate_pull_request.return_value = Mock()
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
            mock_fetch_relevant_files.assert_called_once()
            mock_get_files_to_change.assert_called_once()
            mock_generate_pull_request.assert_called_once()

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.handlers.on_ticket.get_github_client")
    def test_on_ticket_no_files_to_change(self, mock_get_github_client):
        with patch("sweepai.handlers.on_ticket.fetch_relevant_files") as mock_fetch_relevant_files, \
             patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change") as mock_get_files_to_change:
            mock_get_github_client.return_value = (Mock(), Mock())
            mock_fetch_relevant_files.return_value = (Mock(), Mock(), Mock())
            mock_get_files_to_change.return_value = []
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
            mock_fetch_relevant_files.assert_called_once()
            mock_get_files_to_change.assert_called_once()

    @patch("sweepai.handlers.on_ticket.get_github_client")
    def test_on_ticket_generate_pull_request_exception(self, mock_get_github_client):
        with patch("sweepai.handlers.on_ticket.fetch_relevant_files") as mock_fetch_relevant_files, \
             patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change") as mock_get_files_to_change, \
             patch("sweepai.handlers.on_ticket.SweepBot.generate_pull_request") as mock_generate_pull_request:
            mock_get_github_client.return_value = (Mock(), Mock())
            mock_fetch_relevant_files.return_value = (Mock(), Mock(), Mock())
            mock_get_files_to_change.return_value = [Mock()]
            mock_generate_pull_request.side_effect = Exception("Test exception")
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
            mock_fetch_relevant_files.assert_called_once()
            mock_get_files_to_change.assert_called_once()
            mock_generate_pull_request.assert_called_once()
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
        with patch("sweepai.handlers.on_ticket.fetch_relevant_files") as mock_fetch_relevant_files, \
             patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change") as mock_get_files_to_change, \
             patch("sweepai.handlers.on_ticket.SweepBot.generate_pull_request") as mock_generate_pull_request:
            mock_get_github_client.return_value = (Mock(), Mock())
            mock_fetch_relevant_files.return_value = (Mock(), Mock(), Mock())
            mock_get_files_to_change.return_value = [Mock()]
            mock_generate_pull_request.return_value = Mock()
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
            self.assertTrue(result["success"])
            mock_fetch_relevant_files.assert_called_once()
            mock_get_files_to_change.assert_called_once()
            mock_generate_pull_request.assert_called_once()
            mock_handle_payment_logic.assert_called_once_with(
    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.utils.ticket_utils.handle_payment_logic")
    def test_handle_payment_logic_get_files_to_change_empty(
        self, mock_handle_payment_logic, mock_get_github_client
    ):
        with patch("sweepai.handlers.on_ticket.fetch_relevant_files") as mock_fetch_relevant_files, \
             patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change") as mock_get_files_to_change:
            mock_get_github_client.return_value = (Mock(), Mock())
            mock_fetch_relevant_files.return_value = (Mock(), Mock(), Mock())
            mock_get_files_to_change.return_value = []
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
            self.assertFalse(result["success"])
            mock_fetch_relevant_files.assert_called_once()
            mock_get_files_to_change.assert_called_once()
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

    @patch("sweepai.handlers.on_ticket.get_github_client")
    @patch("sweepai.utils.ticket_utils.handle_payment_logic")
    def test_handle_payment_logic_generate_pull_request_exception(
        self, mock_handle_payment_logic, mock_get_github_client
    ):
        with patch("sweepai.handlers.on_ticket.fetch_relevant_files") as mock_fetch_relevant_files, \
             patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change") as mock_get_files_to_change, \
             patch("sweepai.handlers.on_ticket.SweepBot.generate_pull_request") as mock_generate_pull_request:
            mock_get_github_client.return_value = (Mock(), Mock())
            mock_fetch_relevant_files.return_value = (Mock(), Mock(), Mock())
            mock_get_files_to_change.return_value = [Mock()]
            mock_generate_pull_request.side_effect = Exception("Test exception")
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
            self.assertFalse(result["success"])
            mock_fetch_relevant_files.assert_called_once()
            mock_get_files_to_change.assert_called_once()
            mock_generate_pull_request.assert_called_once()
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
        self.assertTrue(result["success"])

        mock_handle_payment_logic.return_value = (False, False, False, Mock())
        with patch("sweepai.handlers.on_ticket.fetch_relevant_files") as mock_fetch_relevant_files, \
             patch("sweepai.handlers.on_ticket.SweepBot.get_files_to_change") as mock_get_files_to_change, \
             patch("sweepai.handlers.on_ticket.SweepBot.generate_pull_request") as mock_generate_pull_request:
            mock_get_github_client.return_value = (Mock(), Mock())
            mock_fetch_relevant_files.return_value = (Mock(), Mock(), Mock())
            mock_get_files_to_change.return_value = [Mock()]
            mock_generate_pull_request.return_value = Mock()
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
            mock_fetch_relevant_files.assert_called_once()
            mock_get_files_to_change.assert_called_once()
            mock_generate_pull_request.assert_called_once()
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
