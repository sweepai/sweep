import unittest
from unittest.mock import Mock

from sweepai.handlers.on_ticket import center


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

    def test_center(self):
        text = "Test text"
        result = center(text)
        self.assertEqual(result, f"<div align='center'>{text}</div>")
