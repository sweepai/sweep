import unittest
from unittest.mock import Mock, patch

from sweepai.handlers.on_ticket import on_ticket, calculate_remaining_tickets, check_user_payment_status


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
    @patch("sweepai.handlers.on_ticket.get_github_client")
    def test_calculate_remaining_tickets(self, mock_get_github_client):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_chat_logger = Mock()
        mock_chat_logger.get_ticket_count.return_value = 10

        # Test case 1: is_consumer_tier=True, is_paying_user=False, use_faster_model=False
        daily_ticket_count, ticket_count = calculate_remaining_tickets(True, False, mock_chat_logger, False)
        self.assertEqual(daily_ticket_count, 3)
        self.assertEqual(ticket_count, 5)

        # Test case 2: is_consumer_tier=False, is_paying_user=True, use_faster_model=False
        daily_ticket_count, ticket_count = calculate_remaining_tickets(False, True, mock_chat_logger, False)
        self.assertEqual(daily_ticket_count, 999)
        self.assertEqual(ticket_count, 490)

        # Test case 3: is_consumer_tier=False, is_paying_user=False, use_faster_model=True
        daily_ticket_count, ticket_count = calculate_remaining_tickets(False, False, mock_chat_logger, True)
        self.assertEqual(daily_ticket_count, 0)
        self.assertEqual(ticket_count, 490)

    @patch("sweepai.handlers.on_ticket.get_github_client")
    def test_check_user_payment_status(self, mock_get_github_client):
        mock_get_github_client.return_value = (Mock(), Mock())
        mock_chat_logger = Mock()
        mock_g = Mock()

        # Test case 1: chat_logger=None, g=None
        is_paying_user, is_consumer_tier = check_user_payment_status(None, None)
        self.assertTrue(is_paying_user)
        self.assertFalse(is_consumer_tier)

        # Test case 2: chat_logger is not None, g=None
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat_logger.is_consumer_tier.return_value = False
        is_paying_user, is_consumer_tier = check_user_payment_status(mock_chat_logger, None)
        self.assertTrue(is_paying_user)
        self.assertFalse(is_consumer_tier)

        # Test case 3: chat_logger is not None, g is not None
        mock_chat_logger.is_paying_user.return_value = False
        mock_chat_logger.is_consumer_tier.return_value = True
        is_paying_user, is_consumer_tier = check_user_payment_status(mock_chat_logger, mock_g)
        self.assertFalse(is_paying_user)
        self.assertTrue(is_consumer_tier)
        self.assertFalse(result["success"])
