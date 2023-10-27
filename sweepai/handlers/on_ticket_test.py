import unittest
from unittest.mock import Mock, patch

from sweepai.handlers.on_ticket import on_ticket, get_github_client, SweepConfig, ClonedRepo, SweepBot, HumanMessagePrompt, ContextPruning, create_pr_changes


class TestOnTicketNewLogic(unittest.TestCase):
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

        self.mock_get_github_client = Mock()
        self.mock_SweepConfig = Mock()
        self.mock_ClonedRepo = Mock()
        self.mock_SweepBot = Mock()
        self.mock_HumanMessagePrompt = Mock()
        self.mock_ContextPruning = Mock()
        self.mock_create_pr_changes = Mock()

        patches = [
            patch('sweepai.handlers.on_ticket.get_github_client', self.mock_get_github_client),
            patch('sweepai.handlers.on_ticket.SweepConfig', self.mock_SweepConfig),
            patch('sweepai.handlers.on_ticket.ClonedRepo', self.mock_ClonedRepo),
            patch('sweepai.handlers.on_ticket.SweepBot', self.mock_SweepBot),
            patch('sweepai.handlers.on_ticket.HumanMessagePrompt', self.mock_HumanMessagePrompt),
            patch('sweepai.handlers.on_ticket.ContextPruning', self.mock_ContextPruning),
            patch('sweepai.handlers.on_ticket.create_pr_changes', self.mock_create_pr_changes),
        ]

        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

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
        self.assertFalse(result["success"])import unittest
from unittest.mock import Mock, patch

from sweepai.handlers.on_ticket import on_ticket, get_github_client, SweepConfig, ClonedRepo, SweepBot, HumanMessagePrompt, ContextPruning, create_pr_changes


class TestOnTicketNewLogic(unittest.TestCase):
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

        self.mock_get_github_client = Mock()
        self.mock_SweepConfig = Mock()
        self.mock_ClonedRepo = Mock()
        self.mock_SweepBot = Mock()
        self.mock_HumanMessagePrompt = Mock()
        self.mock_ContextPruning = Mock()
        self.mock_create_pr_changes = Mock()

        patches = [
            patch('sweepai.handlers.on_ticket.get_github_client', self.mock_get_github_client),
            patch('sweepai.handlers.on_ticket.SweepConfig', self.mock_SweepConfig),
            patch('sweepai.handlers.on_ticket.ClonedRepo', self.mock_ClonedRepo),
            patch('sweepai.handlers.on_ticket.SweepBot', self.mock_SweepBot),
            patch('sweepai.handlers.on_ticket.HumanMessagePrompt', self.mock_HumanMessagePrompt),
            patch('sweepai.handlers.on_ticket.ContextPruning', self.mock_ContextPruning),
            patch('sweepai.handlers.on_ticket.create_pr_changes', self.mock_create_pr_changes),
        ]

        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

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
    def test_on_ticket_new_logic(self):
        self.mock_get_github_client.return_value = (Mock(), Mock())
        self.mock_SweepConfig.get_config.return_value = {}
        self.mock_ClonedRepo.get_num_files_from_repo.return_value = 10
        self.mock_SweepBot.get_files_to_change.return_value = ([], [])
        self.mock_SweepBot.generate_pull_request.return_value = Mock()
        self.mock_create_pr_changes.return_value = {"success": True, "pull_request": Mock()}

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
        self.mock_get_github_client.assert_called_once_with(self.issue.installation_id)
        self.mock_SweepConfig.get_config.assert_called_once()
        self.mock_ClonedRepo.get_num_files_from_repo.assert_called_once()
        self.mock_SweepBot.get_files_to_change.assert_called_once()
        self.mock_SweepBot.generate_pull_request.assert_called_once()
        self.mock_create_pr_changes.assert_called_once()
