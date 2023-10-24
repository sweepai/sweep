import unittest
from unittest.mock import Mock, patch

from sweepai.api import run_on_check_suite


class TestAPI(unittest.TestCase):
    @patch("sweepai.api.get_github_client")
    @patch("sweepai.api.on_check_suite")
    def test_check_run_event_handler(self, mock_on_check_suite, mock_get_github_client):
        # Arrange
        mock_request = Mock()
        mock_request.check_run.pull_requests = [Mock()]
        mock_request.repository.full_name = "test/repo"
        mock_request.installation.id = 123
        mock_on_check_suite.return_value = None
        mock_get_github_client.return_value = (None, Mock())

        # Act
        run_on_check_suite(request=mock_request)

        # Assert
        mock_on_check_suite.assert_called_once_with(mock_request)
