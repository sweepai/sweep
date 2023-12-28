import unittest
from unittest.mock import MagicMock, patch

from sweepai.handlers.on_comment import on_comment


class OnCommentTest(unittest.TestCase):

    @patch('sweepai.handlers.on_comment.get_github_client')
    @patch('sweepai.handlers.on_comment.MockPR')
    def test_issue_number_match(self, mock_get_github_client, mock_MockPR):
        mock_get_github_client.return_value = (None, MagicMock())
        mock_MockPR.return_value = MagicMock()

        # Test when pr_body is None
        result = on_comment(
            repo_full_name='test/repo',
            repo_description='Test Repo',
            comment='Test Comment',
            pr_path=None,
            pr_line_position=None,
            username='testuser',
            installation_id=123,
        )
        self.assertIsNone(result['issue_number'])

        # Test when pr_body contains "Fixes #1234."
        result = on_comment(
            repo_full_name='test/repo',
            repo_description='Test Repo',
            comment='Test Comment',
            pr_path=None,
            pr_line_position=None,
            username='testuser',
            installation_id=123,
            pr_body='Fixes #1234.'
        )
        self.assertEqual(result['issue_number'], '1234')
