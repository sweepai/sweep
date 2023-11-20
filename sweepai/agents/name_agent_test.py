import unittest
from unittest.mock import patch

from sweepai.agents.name_agent import NameBot


class TestNameBotNameFunctions(unittest.TestCase):
    @patch("sweepai.utils.chat_logger.ChatLogger.is_paying_user")
    @patch("sweepai.core.chat.ChatGPT.chat")
    def test_name_functions(self, mock_chat, mock_is_paying_user):
        mock_is_paying_user.return_value = True
        mock_chat.return_value = "<function_name>\nmock_function_name\n</function_name>"

        bot = NameBot()
        function_names = bot.name_functions("old_code", "snippets", "existing_names", 1)

        self.assertEqual(function_names, ["mock_function_name"])

    @patch("sweepai.utils.chat_logger.ChatLogger.is_paying_user")
    @patch("sweepai.core.chat.ChatGPT.chat")
    def test_name_functions_non_paying_user(self, mock_chat, mock_is_paying_user):
        mock_is_paying_user.return_value = False
        mock_chat.return_value = "<function_name>\nmock_function_name\n</function_name>"

        bot = NameBot()
        function_names = bot.name_functions("old_code", "snippets", "existing_names", 1)

        self.assertEqual(function_names, ["mock_function_name"])


if __name__ == "__main__":
    unittest.main()

