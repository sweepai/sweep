import unittest
from unittest.mock import MagicMock, patch

from sweepai.handlers.on_merge_conflict import on_merge_conflict


class TestOnMergeConflict(unittest.TestCase):
    @patch('sweepai.handlers.on_merge_conflict.get_github_client')
    @patch('sweepai.handlers.on_merge_conflict.ClonedRepo')
    @patch('sweepai.handlers.on_merge_conflict.TicketProgress')
    @patch('sweepai.handlers.on_merge_conflict.ChatLogger')
    @patch('sweepai.handlers.on_merge_conflict.create_pr_changes')
    @patch('sweepai.handlers.on_merge_conflict.get_branch_diff_text')
    @patch('sweepai.handlers.on_merge_conflict.PRDescriptionBot')
    def test_request_string_formatting(self, mock_get_github_client, mock_ClonedRepo, mock_TicketProgress, mock_ChatLogger, mock_create_pr_changes, mock_get_branch_diff_text, mock_PRDescriptionBot):
        mock_get_github_client.return_value = ('token', MagicMock())
        mock_ClonedRepo.return_value = MagicMock()
        mock_TicketProgress.return_value = MagicMock()
        mock_ChatLogger.return_value = MagicMock()
        mock_create_pr_changes.return_value = iter([{'success': True}])
        mock_get_branch_diff_text.return_value = 'diff_text'
        mock_PRDescriptionBot.return_value.describe_diffs.return_value = 'description'

        pr = MagicMock()
        pr.title = 'Test PR'
        pr.number = 123
        pr.head.ref = 'test_branch'
        pr.base.ref = 'base_branch'
        pr.html_url = 'http://test_url'
        pr.create_issue_comment.return_value = MagicMock()

        mock_get_github_client.return_value[1].get_repo.return_value.get_pull.return_value = pr

        result = on_merge_conflict(pr_number=123, username='test_user', repo_full_name='test_repo', installation_id=1, tracking_id='test_tracking_id')

        self.assertEqual(result, {'success': True})
        self.assertIn('Sweep: Resolve merge conflicts for PR #123: Test PR', pr.create_issue_comment.call_args[0][0])
