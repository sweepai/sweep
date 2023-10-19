import unittest
from unittest.mock import Mock, patch
from sweepai.utils.docker_utils import get_latest_docker_version
from sweepai.utils.github_utils import add_badge_to_issue

class TestAPI(unittest.TestCase):
    @patch('sweepai.utils.github_utils.add_badge_to_issue')
    def test_docker_version_badge_added(self, mock_add_badge_to_issue):
        mock_issue = Mock()
        mock_issue.full_name = 'sweepai/sweep'
        mock_issue.number = 1

        docker_version_badge = get_latest_docker_version()
        add_badge_to_issue(mock_issue.full_name, mock_issue.number, docker_version_badge)

        mock_add_badge_to_issue.assert_called_with(mock_issue.full_name, mock_issue.number, docker_version_badge)
        self.assertIn(docker_version_badge, mock_issue.body)
        self.assertIn(docker_version_badge, mock_issue.comments)
