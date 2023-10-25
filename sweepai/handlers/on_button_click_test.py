import unittest
from unittest.mock import patch, MagicMock
from sweepai.handlers.on_button_click import handle_button_click
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import get_github_client

class TestOnButtonClick(unittest.TestCase):
    @patch('sweepai.handlers.on_button_click.MONGODB_URI')
    @patch('sweepai.handlers.on_button_click.ChatLogger')
    @patch('sweepai.utils.github_utils.get_github_client')
    def test_handle_button_click(self, mock_get_github_client, mock_chat_logger, mock_mongodb_uri):
        # Mock the MONGODB_URI environment variable
        mock_mongodb_uri.return_value = 'mongodb://localhost:27017'

        # Mock request dictionary
        request_dict = {
            "action": "mock_action",
            "issue": {
                "number": 1,
                "title": "mock_title",
                "html_url": "mock_html_url",
                "user": {"login": "mock_issue_user", "type": "User"},
                "labels": [{"name": "mock_label"}]
            },
            "repository": {"full_name": "mock_repo"},
            "sender": {"login": "mock_user", "type": "User"},
            "comment": {
                "body": "mock_comment",
                "user": {"login": "mock_comment_user", "type": "User"},
                "id": 12345
            },
            "installation": {"id": 12345}
        }

        # Mock the get_github_client function
        mock_token = 'mock_token'
        mock_gh_client = MagicMock()
        mock_get_github_client.return_value = (mock_token, mock_gh_client)
        
        # Mock the ChatLogger class
        mock_chat_logger_instance = MagicMock()
        mock_chat_logger.return_value = mock_chat_logger_instance
        
        # Assert that the get_github_client function was called with the correct arguments
        mock_get_github_client.assert_called_with(request_dict["installation"]["id"])

        # Call the handle_button_click function
        handle_button_click(request_dict)

        # Assert that the ChatLogger class was called with the correct arguments
        mock_chat_logger.assert_called_with({'username': 'mock_user'})

        # Assert that the chat_logger object was initialized correctly
        self.assertIsNotNone(mock_chat_logger_instance.chat_collection)
        self.assertIsNotNone(mock_chat_logger_instance.ticket_collection)

if __name__ == '__main__':
    unittest.main()
