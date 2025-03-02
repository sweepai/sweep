import unittest
from unittest.mock import Mock, patch

from sweepai.handlers.on_merge_conflict import on_merge_conflict


class TestOnMergeConflict(unittest.TestCase):
    @patch('sweepai.handlers.on_merge_conflict.get_github_client')
    @patch('sweepai.handlers.on_merge_conflict.ClonedRepo')
    @patch('sweepai.handlers.on_merge_conflict.TicketProgress')
    @patch('sweepai.handlers.on_merge_conflict.ChatLogger')
    def test_edit_comment(self, MockGetGithubClient, MockClonedRepo, MockTicketProgress, MockChatLogger):
        pr_number = 1
        username = 'test_user'
        repo_full_name = 'test_repo'
        installation_id = 123
        tracking_id = 'test_tracking_id'

        MockGetGithubClient.return_value = (Mock(), Mock())
        MockClonedRepo.return_value = Mock()
        MockTicketProgress.return_value = Mock()
        MockChatLogger.return_value = Mock()

        on_merge_conflict(pr_number, username, repo_full_name, installation_id, tracking_id)

        MockGetGithubClient.assert_called_once_with(installation_id=installation_id)
        MockClonedRepo.assert_called_once()
        MockTicketProgress.assert_called_once()
        MockChatLogger.assert_called_once()

    @patch('sweepai.handlers.on_merge_conflict.get_github_client')
    @patch('sweepai.handlers.on_merge_conflict.ClonedRepo')
    @patch('sweepai.handlers.on_merge_conflict.TicketProgress')
    @patch('sweepai.handlers.on_merge_conflict.ChatLogger')
    def test_pr_description(self, MockGetGithubClient, MockClonedRepo, MockTicketProgress, MockChatLogger):
        pr_number = 1
        username = 'test_user'
        repo_full_name = 'test_repo'
        installation_id = 123
        tracking_id = 'test_tracking_id'

        MockGetGithubClient.return_value = (Mock(), Mock())
        MockClonedRepo.return_value = Mock()
        MockTicketProgress.return_value = Mock()
        MockChatLogger.return_value = Mock()

        on_merge_conflict(pr_number, username, repo_full_name, installation_id, tracking_id)

        MockGetGithubClient.assert_called_once_with(installation_id=installation_id)
        MockClonedRepo.assert_called_once()
        MockTicketProgress.assert_called_once()
        MockChatLogger.assert_called_once()

if __name__ == '__main__':
    unittest.main()
