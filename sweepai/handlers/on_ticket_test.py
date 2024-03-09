import unittest
from unittest.mock import MagicMock, patch

from sweepai.handlers import on_ticket


class TestOnTicket(unittest.TestCase):

    @patch('sweepai.handlers.on_ticket.LogtailHandler')
    @patch('sweepai.handlers.on_ticket.get_github_client')
    @patch('sweepai.handlers.on_ticket.ClonedRepo')
    @patch('sweepai.handlers.on_ticket.ChatLogger')
    @patch('sweepai.handlers.on_ticket.SweepBot')
    @patch('sweepai.handlers.on_ticket.posthog')
    def test_on_ticket_active_flag(self, mock_posthog, mock_sweep_bot, mock_chat_logger, mock_cloned_repo, mock_get_github_client, mock_logtail_handler):
        mock_title = 'test_title'
        mock_summary = 'test_summary'
        mock_issue_number = 1
        mock_issue_url = 'test_url'
        mock_username = 'test_user'
        mock_repo_full_name = 'test/repo'
        mock_repo_description = 'Test repo'
        mock_installation_id = 123
        mock_comment_id = 1
        mock_edited = False
        mock_tracking_id = 'test_tracking_id'

        mock_get_github_client.return_value = (None, MagicMock())
        mock_cloned_repo.return_value = MagicMock()
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat_logger.use_faster_model.return_value = False
        mock_sweep_bot.from_system_message_content.return_value = MagicMock()
        mock_posthog.capture.return_value = None

        result = on_ticket.on_ticket(
            mock_title,
            mock_summary,
            mock_issue_number,
            mock_issue_url,
            mock_username,
            mock_repo_full_name,
            mock_repo_description,
            mock_installation_id,
            mock_comment_id,
            mock_edited,
            mock_tracking_id
        )

        self.assertEqual(result, {'success': True})

if __name__ == '__main__':
    unittest.main()
