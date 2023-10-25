import unittest
from unittest.mock import patch, MagicMock
from sweepai.handlers.on_button_click import handle_button_click
from sweepai.utils.chat_logger import ChatLogger

class TestOnButtonClick(unittest.TestCase):
    @patch('sweepai.handlers.on_button_click.MONGODB_URI')
    @patch('sweepai.handlers.on_button_click.ChatLogger')
    def test_handle_button_click(self, mock_chat_logger, mock_mongodb_uri):
        # Mock the MONGODB_URI environment variable
        mock_mongodb_uri.return_value = 'mongodb://localhost:27017'

        # Mock the ChatLogger class
        mock_chat_logger_instance = MagicMock()
        mock_chat_logger.return_value = mock_chat_logger_instance

        # Call the handle_button_click function
        handle_button_click({})

        # Assert that the ChatLogger class was called with the correct arguments
        mock_chat_logger.assert_called_with({'username': None})

        # Assert that the chat_logger object was initialized correctly
        self.assertIsNotNone(mock_chat_logger_instance.chat_collection)
        self.assertIsNotNone(mock_chat_logger_instance.ticket_collection)

if __name__ == '__main__':
    unittest.main()
