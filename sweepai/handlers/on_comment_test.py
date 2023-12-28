import unittest
from unittest.mock import MagicMock, patch

from sweepai.handlers.on_comment import on_comment


class TestOnComment(unittest.TestCase):
    @patch('sweepai.handlers.on_comment.posthog.capture')
    @patch('sweepai.handlers.on_comment.get_github_client')
    def test_on_comment(self, mock_get_github_client, mock_posthog_capture):
        mock_get_github_client.return_value = (MagicMock(), MagicMock())
        mock_posthog_capture.return_value = None

        on_comment(
            repo_full_name='test/repo',
            repo_description='Test Repo',
            comment='Test Comment',
            pr_path='test/path',
            pr_line_position=1,
            username='testuser',
            installation_id=1,
            pr_number=1,
            comment_id=1,
            chat_logger=None,
            pr=None,
            repo=None,
            comment_type='comment',
            type='comment',
            tracking_id='test_tracking_id'
        )

        mock_posthog_capture.assert_called_with(
            'testuser',
            'started',
            properties={
                'repo_full_name': 'test/repo',
                'repo_name': 'repo',
                'organization': 'test',
                'repo_description': 'Test Repo',
                'installation_id': 1,
                'username': 'testuser',
                'function': 'on_comment',
                'model': 'gpt-4',
                'tier': 'free',
                'mode': 'test',
                'pr_path': 'test/path',
                'pr_line_position': 1,
                'pr_number': 1,
                'pr_html_url': None,
                'comment_id': 1,
                'comment': 'Test Comment',
                'issue_number': '',
                'tracking_id': 'test_tracking_id',
                'duration': unittest.mock.ANY
            }
        )

        mock_get_github_client.assert_called_with(1)
