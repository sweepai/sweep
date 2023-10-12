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

    @patch('sweepai.handlers.on_ticket.get_github_client')
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
            self.issue.installation_id
        )
        self.assertTrue(result['success'])

    @patch('sweepai.handlers.on_ticket.get_github_client')
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
            self.issue.installation_id
        )
        self.assertFalse(result['success'])
