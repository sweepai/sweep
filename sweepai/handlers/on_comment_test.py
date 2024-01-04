import unittest
from unittest.mock import MagicMock, patch

from sweepai.handlers import on_comment


class TestOnComment(unittest.TestCase):

    @patch('sweepai.handlers.on_comment.get_github_client')
    @patch('sweepai.handlers.on_comment.ClonedRepo')
    @patch('sweepai.handlers.on_comment.ChatLogger')
    @patch('sweepai.handlers.on_comment.SweepBot')
    @patch('sweepai.handlers.on_comment.posthog')
    def test_on_comment_active_flag(self, mock_posthog, mock_sweep_bot, mock_chat_logger, mock_cloned_repo, mock_get_github_client):
        mock_repo_full_name = 'test/repo'
        mock_repo_description = 'Test repo'
        mock_comment = 'Test comment'
        mock_pr_path = None
        mock_pr_line_position = None
        mock_username = 'test_user'
        mock_installation_id = 123
        mock_pr_number = 1
        mock_comment_id = None
        mock_chat_logger = MagicMock()
        mock_pr = MagicMock()
        mock_repo = MagicMock()
        mock_comment_type = 'comment'
        mock_type = 'comment'
        mock_tracking_id = 'test_tracking_id'

        mock_get_github_client.return_value = (None, MagicMock())
        mock_cloned_repo.return_value = MagicMock()
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat_logger.use_faster_model.return_value = False
        mock_sweep_bot.from_system_message_content.return_value = MagicMock()
        mock_posthog.capture.return_value = None

        result = on_comment.on_comment(
            mock_repo_full_name,
            mock_repo_description,
            mock_comment,
            mock_pr_path,
            mock_pr_line_position,
            mock_username,
            mock_installation_id,
            mock_pr_number,
            mock_comment_id,
            mock_chat_logger,
            mock_pr,
            mock_repo,
            mock_comment_type,
            mock_type,
            mock_tracking_id
        )

        self.assertEqual(result, {'success': True})

if __name__ == '__main__':
    unittest.main()
