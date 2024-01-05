import unittest
from unittest.mock import Mock, patch

from sweepai.core.chat import DEFAULT_GPT35_MODEL, Chat


class TestChat(unittest.TestCase):
    def setUp(self):
        self.chat = Chat()
        self.chat.chat_logger = Mock()

    def tearDown(self):
        del self.chat

    @patch('sweepai.core.chat.ChatLogger')
    def test_call_openai_with_non_active_user(self, mock_chat_logger):
        mock_chat_logger.active = False
        mock_chat_logger.is_paying_user.return_value = False
        mock_chat_logger.is_consumer_tier.return_value = False
        model = self.chat.call_openai()
        self.assertEqual(model, DEFAULT_GPT35_MODEL)

    @patch('sweepai.core.chat.ChatLogger')
    def test_call_openai_with_paying_user(self, mock_chat_logger):
        mock_chat_logger.active = True
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat_logger.get_ticket_count.return_value = 100
        model = self.chat.call_openai()
        self.assertEqual(model, self.chat.model)

    @patch('sweepai.core.chat.ChatLogger')
    def test_call_openai_with_purchased_tickets(self, mock_chat_logger):
        mock_chat_logger.active = True
        mock_chat_logger.is_paying_user.return_value = False
        mock_chat_logger.get_ticket_count.return_value = 200
        mock_chat_logger.get_ticket_count(purchased=True).return_value = 10
        model = self.chat.call_openai()
        self.assertEqual(model, self.chat.model)

if __name__ == '__main__':
    unittest.main()
