import unittest
from unittest.mock import MagicMock, patch

from sweepai.handlers.on_merge_conflict import on_merge_conflict


class TestOnMergeConflict(unittest.TestCase):

    @patch('sweepai.handlers.on_merge_conflict.get_github_client')
    @patch('sweepai.handlers.on_merge_conflict.ClonedRepo')
    @patch('sweepai.handlers.on_merge_conflict.TicketProgress')
    @patch('sweepai.handlers.on_merge_conflict.ChatLogger')
    @patch('sweepai.handlers.on_merge_conflict.create_pr_changes')
    def test_on_merge_conflict_success(self, mock_create_pr_changes, mock_chat_logger, mock_ticket_progress, mock_cloned_repo, mock_get_github_client):
        mock_get_github_client.return_value = (MagicMock(), MagicMock())
        mock_cloned_repo.return_value = MagicMock()
        mock_ticket_progress.return_value = MagicMock()
        mock_chat_logger.return_value = MagicMock()
        mock_create_pr_changes.return_value = [{}]

        result = on_merge_conflict(1, 'username', 'repo_full_name', 1, 'tracking_id')

        self.assertEqual(result, {"success": True})
        mock_get_github_client.assert_called_once_with(installation_id=1)
        mock_cloned_repo.assert_called_once()
        mock_ticket_progress.assert_called_once()
        mock_chat_logger.assert_called_once()
        mock_create_pr_changes.assert_called_once()

    @patch('sweepai.handlers.on_merge_conflict.get_github_client')
    def test_on_merge_conflict_exception(self, mock_get_github_client):
        mock_get_github_client.side_effect = Exception('Test exception')

        result = on_merge_conflict(1, 'username', 'repo_full_name', 1, 'tracking_id')

        self.assertEqual(result, {"success": False})
        mock_get_github_client.assert_called_once_with(installation_id=1)

if __name__ == '__main__':
    unittest.main()
