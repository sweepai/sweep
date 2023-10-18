import unittest
from unittest.mock import Mock, patch
import hashlib
from time import time
from sweepai.handlers import on_ticket

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

    @patch('sweepai.handlers.on_ticket.get_github_client')
    def test_on_ticket(self, mock_get_github_client):
        mock_get_github_client.return_value = (Mock(), Mock())
        result = on_ticket.on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id
        )
        self.assertTrue(result['success'])

    @patch('sweepai.handlers.on_ticket.get_github_client')
    def test_on_ticket_with_exception(self, mock_get_github_client):
        mock_get_github_client.side_effect = Exception("Test exception")
        result = on_ticket.on_ticket(
            self.issue.title,
            self.issue.summary,
            self.issue.issue_number,
            self.issue.issue_url,
            self.issue.username,
            self.issue.repo_full_name,
            self.issue.repo_description,
            self.issue.installation_id
        )
        self.assertFalse(result['success'])

    @patch('sweepai.handlers.on_ticket.time')
    def test_tracking_id_generation(self, mock_time):
        mock_time.return_value = 1234567890.123456
        expected_tracking_id = hashlib.sha256(str(mock_time.return_value).encode()).hexdigest()
        on_ticket.on_ticket(123, 456, False)
        self.assertEqual(on_ticket.tracking_id, expected_tracking_id)

    @patch('sweepai.handlers.on_ticket.metadata')
    def test_tracking_id_in_metadata(self, mock_metadata):
        on_ticket.on_ticket(123, 456, False)
        self.assertIn('tracking_id', mock_metadata)

    @patch('sweepai.handlers.on_ticket.logger')
    def test_tracking_id_in_log_messages(self, mock_logger):
        on_ticket.on_ticket(123, 456, False)
        mock_logger.warning.assert_called_with(f"(tracking ID: {on_ticket.tracking_id}) System exit")
        mock_logger.error.assert_called_with(f"(tracking ID: {on_ticket.tracking_id}) {Exception}")

if __name__ == '__main__':
    unittest.main()
