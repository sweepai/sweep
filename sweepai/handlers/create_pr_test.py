import unittest
from unittest.mock import Mock, patch
from sweepai.handlers.create_pr import create_pr
from sweepai.core.entities import FileChangeRequest, MaxTokensExceeded, MockPR, PullRequest, SweepBot

class TestCreatePR(unittest.TestCase):
    def setUp(self):
        self.sweep_bot = SweepBot(Mock(), Mock())
        self.pull_request = PullRequest("title", "content")
        self.file_change_request = FileChangeRequest("entity", "instructions", "change_type")

    @patch.object(SweepBot, 'change_files_in_github_iterator')
    def test_create_pr_with_file_change_requests(self, mock_change_files_in_github_iterator):
        mock_change_files_in_github_iterator.return_value = [(self.file_change_request, 1, None, Mock(), [self.file_change_request])]
        result = create_pr([self.file_change_request], self.pull_request, self.sweep_bot, "username", 12345)
        self.assertTrue(result["success"])

    @patch.object(SweepBot, 'repo')
    def test_create_pr_with_get_commits_response(self, mock_repo):
        mock_repo.get_commits.return_value = Mock(totalCount=0)
        result = create_pr([self.file_change_request], self.pull_request, self.sweep_bot, "username", 12345)
        self.assertFalse(result["success"])

    @patch.object(SweepBot, 'repo')
    def test_create_pr_with_get_git_ref_response(self, mock_repo):
        mock_repo.get_git_ref.return_value = Mock()
        result = create_pr([self.file_change_request], self.pull_request, self.sweep_bot, "username", 12345)
        self.assertTrue(result["success"])

    def test_create_pr_with_pull_requests(self):
        result = create_pr([self.file_change_request], self.pull_request, self.sweep_bot, "username", 12345)
        self.assertTrue(result["success"])

    @patch.object(SweepBot, 'change_files_in_github_iterator')
    def test_create_pr_with_exceptions(self, mock_change_files_in_github_iterator):
        mock_change_files_in_github_iterator.side_effect = MaxTokensExceeded("Max tokens exceeded")
        with self.assertRaises(MaxTokensExceeded):
            create_pr([self.file_change_request], self.pull_request, self.sweep_bot, "username", 12345)
