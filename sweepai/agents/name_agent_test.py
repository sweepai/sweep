import unittest
from unittest.mock import patch

from sweepai.agents.name_agent import NameBot
from sweepai.config.server import DEFAULT_GPT35_MODEL


class TestNameBotNameFunctions(unittest.TestCase):
    @patch("sweepai.utils.chat_logger.ChatLogger.is_paying_user")
    @patch("sweepai.core.chat.ChatGPT.chat")
    def test_name_functions(self, mock_chat, mock_is_paying_user):
        mock_is_paying_user.return_value = True
        mock_chat.return_value = "<function_name>\nmock_function_name\n</function_name>"

        name_bot = NameBot()
        old_code = "def old_function(): pass"
        snippets = ["def snippet(): pass"]
        existing_names = ["old_function"]
        count = 1

        function_names = name_bot.name_functions(
            old_code, snippets, existing_names, count
        )

        self.assertEqual(function_names, ["mock_function_name"])

    @patch("sweepai.utils.chat_logger.ChatLogger.is_paying_user")
    @patch("sweepai.core.chat.ChatGPT.chat")
    def test_name_functions_non_paying_user(self, mock_chat, mock_is_paying_user):
        mock_is_paying_user.return_value = False
        mock_chat.return_value = "<function_name>\nmock_function_name\n</function_name>"

        name_bot = NameBot()
        old_code = "def old_function(): pass"
        snippets = ["def snippet(): pass"]
        existing_names = ["old_function"]
        count = 1

        function_names = name_bot.name_functions(
            old_code, snippets, existing_names, count
        )

        self.assertEqual(function_names, ["mock_function_name"])
        self.assertEqual(name_bot.model, DEFAULT_GPT35_MODEL)


if __name__ == "__main__":
    unittest.main()

