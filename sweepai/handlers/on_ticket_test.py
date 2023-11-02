import unittest
from unittest.mock import Mock, patch

from sweepai.utils.ticket_utils import construct_payment_message
from sweepai.handlers.on_ticket import on_ticket
class TestConstructPaymentMessage(unittest.TestCase):
    def setUp(self):
        self.user_type = "Sweep Pro"
        self.model_name = "GPT-3.5"
        self.ticket_count = 500
        self.daily_ticket_count = 999
        self.is_paying_user = True

    @patch("sweepai.handlers.on_ticket.ChatLogger")
    def test_construct_payment_message_paying_user(self, mock_chat_logger):
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat_logger.get_ticket_count.return_value = 500
        result = construct_payment_message(
            self.user_type,
            self.model_name,
            self.ticket_count,
            self.daily_ticket_count,
            self.is_paying_user
        )
        self.assertIn("Sweep Pro", result)
        self.assertIn("GPT-3.5", result)
        self.assertIn("unlimited GPT-4 tickets", result)

    @patch("sweepai.handlers.on_ticket.ChatLogger")
    def test_construct_payment_message_non_paying_user(self, mock_chat_logger):
        mock_chat_logger.is_paying_user.return_value = False
        mock_chat_logger.get_ticket_count.return_value = 0
        result = construct_payment_message(
            self.user_type,
            self.model_name,
            self.ticket_count,
            self.daily_ticket_count,
            self.is_paying_user
        )
        self.assertIn("Sweep Pro", result)
        self.assertIn("GPT-3.5", result)
        self.assertIn("0 GPT-4 tickets left for the month", result)
        self.assertIn("For more GPT-4 tickets, visit", result)
    
    @patch("sweepai.handlers.on_ticket.ChatLogger")
    def test_construct_payment_message_different_models(self, mock_chat_logger):
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat_logger.get_ticket_count.return_value = 500
        self.model_name = "GPT-4"
        result = construct_payment_message(
            self.user_type,
            self.model_name,
            self.ticket_count,
            self.daily_ticket_count,
            self.is_paying_user
        )
        self.assertIn("Sweep Pro", result)
        self.assertIn("GPT-4", result)
        self.assertIn("unlimited GPT-4 tickets", result)


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

if __name__ == '__main__':
    unittest.main()

    @patch("sweepai.handlers.on_ticket.get_github_client")
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
