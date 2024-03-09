import unittest
from unittest.mock import MagicMock

from sweepai.utils import chat_logger


class TestChatLogger(unittest.TestCase):

    def test_use_faster_model(self):
        mock_chat_logger = MagicMock()

        # Test case when user is paying, ticket count is less than 500 and active is True
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat_logger.get_ticket_count.return_value = 499
        mock_chat_logger.active = True
        self.assertEqual(chat_logger.ChatLogger.use_faster_model(mock_chat_logger), True)

        # Test case when user is paying, ticket count is 500 and active is True
        mock_chat_logger.get_ticket_count.return_value = 500
        self.assertEqual(chat_logger.ChatLogger.use_faster_model(mock_chat_logger), False)

        # Test case when user is on consumer tier, ticket count is less than 20 and active is True
        mock_chat_logger.is_paying_user.return_value = False
        mock_chat_logger.is_consumer_tier.return_value = True
        mock_chat_logger.get_ticket_count.return_value = 19
        self.assertEqual(chat_logger.ChatLogger.use_faster_model(mock_chat_logger), True)

        # Test case when user is on consumer tier, ticket count is 20 and active is True
        mock_chat_logger.get_ticket_count.return_value = 20
        self.assertEqual(chat_logger.ChatLogger.use_faster_model(mock_chat_logger), False)

        # Test case when user is neither paying nor on consumer tier, ticket count is less than 5 and active is True
        mock_chat_logger.is_consumer_tier.return_value = False
        mock_chat_logger.get_ticket_count.return_value = 4
        self.assertEqual(chat_logger.ChatLogger.use_faster_model(mock_chat_logger), True)

        # Test case when user is neither paying nor on consumer tier, ticket count is 5 and active is True
        mock_chat_logger.get_ticket_count.return_value = 5
        self.assertEqual(chat_logger.ChatLogger.use_faster_model(mock_chat_logger), False)

if __name__ == '__main__':
    unittest.main()
