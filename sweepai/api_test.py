import unittest
from unittest.mock import Mock, patch

from sweepai.api import update_sweep_prs_v2
from sweepai.utils.github_utils import get_github_client


class TestMergePullRequests(unittest.TestCase):
    @patch("sweepai.api.get_github_client")
    @patch("sweepai.api.logger.warning")
    def test_merge_pull_requests(self, mock_logger_warning, mock_get_github_client):
        mock_pr = Mock()
        mock_pr.head.ref = "sweep/test"
        mock_pr.mergeable_state = "clean"
        mock_pr.created_at.timestamp.return_value = 0
        mock_pr.title = "[Sweep Rules] Test"
        mock_pr.edit.return_value = None
        mock_pr.number = 1
        mock_pr.merged = False

        mock_repo = Mock()
        mock_repo.merge.return_value = None
        mock_repo.get_pull.return_value = mock_pr

        mock_g = Mock()
        mock_g.get_repo.return_value = mock_repo

        mock_get_github_client.return_value = (None, mock_g)

        update_sweep_prs_v2("test/test", 1)

        mock_repo.merge.assert_called_once_with(
            mock_pr.head.ref,
            mock_repo.default_branch,
            f"Merge main into {mock_pr.head.ref}",
        )
        mock_logger_warning.assert_not_called()

    @patch("sweepai.api.get_github_client")
    @patch("sweepai.api.logger.warning")
    def test_merge_pull_requests_exception(self, mock_logger_warning, mock_get_github_client):
        mock_pr = Mock()
        mock_pr.head.ref = "sweep/test"
        mock_pr.mergeable_state = "clean"
        mock_pr.created_at.timestamp.return_value = 0
        mock_pr.title = "[Sweep Rules] Test"
        mock_pr.edit.return_value = None
        mock_pr.number = 1
        mock_pr.merged = False

        mock_repo = Mock()
        mock_repo.merge.side_effect = Exception("Test exception")
        mock_repo.get_pull.return_value = mock_pr

        mock_g = Mock()
        mock_g.get_repo.return_value = mock_repo

        mock_get_github_client.return_value = (None, mock_g)

        update_sweep_prs_v2("test/test", 1)

        mock_logger_warning.assert_called_once_with(
            f"Failed to merge changes from default branch into PR #{mock_pr.number}: Test exception"
        )

if __name__ == "__main__":
    unittest.main()
