import unittest
from unittest.mock import MagicMock, patch

from sweepai.handlers.on_comment import on_comment


class TestOnComment(unittest.TestCase):
    @patch("sweepai.handlers.on_comment.get_github_client")
    @patch("sweepai.handlers.on_comment.ChatLogger")
    def test_on_comment_tracking_id(self, mock_get_github_client, mock_ChatLogger):
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_get_github_client.return_value = ("token", mock_repo)
        mock_ChatLogger.return_value = MagicMock()

        tracking_id = "test_tracking_id"
        on_comment(
            repo_full_name="test/repo",
            repo_description="Test Repo",
            comment="Test Comment",
            pr_path=None,
            pr_line_position=None,
            username="test_user",
            installation_id=123,
            pr_number=None,
            comment_id=None,
            chat_logger=None,
            pr=mock_pr,
            repo=mock_repo,
            comment_type="comment",
            type="comment",
            tracking_id=tracking_id,
        )

        metadata = mock_get_github_client.call_args[1]
        self.assertEqual(metadata["tracking_id"], tracking_id)

if __name__ == "__main__":
    unittest.main()
