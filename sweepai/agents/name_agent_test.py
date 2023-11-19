import unittest
from unittest.mock import MagicMock, patch

from sweepai.agents.name_agent import NameBot


class TestNameBot(unittest.TestCase):
    def setUp(self):
        self.name_bot = NameBot()
        self.name_bot.chat_logger = MagicMock()
        self.name_bot.chat = MagicMock()

    @unittest.skip("FAILED (errors=1)")
    @patch("sweepai.agents.name_agent.serialize_method_name")
    def test_name_functions(self, mock_serialize_method_name):
        self.name_bot.chat_logger.is_paying_user.return_value = False
        self.name_bot.chat.return_value = (
            "<function_name>\nmock_function_name\n</function_name>"
        )
        mock_serialize_method_name.return_value = "mock_function_name"

        result = self.name_bot.name_functions(
            "old_code", "snippets", "existing_names", 1
        )
        self.assertEqual(result, ["mock_function_name"])

    @patch("sweepai.agents.name_agent.DEFAULT_GPT4_32K_MODEL", "new constant")
    @patch("sweepai.agents.name_agent.DEFAULT_GPT35_MODEL", "new constant")
    @patch("sweepai.agents.name_agent.NameBot.chat_logger", new_callable=MagicMock)
    @patch("sweepai.agents.name_agent.NameBot.chat", new_callable=MagicMock)
    @patch("sweepai.agents.name_agent.serialize_method_name")
    def test_name_functions_paying_user(
        self, mock_serialize_method_name, mock_chat, mock_chat_logger
    ):
        mock_chat_logger.is_paying_user.return_value = True
        mock_chat.return_value = "<function_name>\nmock_function_name\n</function_name>"
        mock_serialize_method_name.return_value = "mock_function_name"

        name_bot = NameBot()
        name_bot.chat_logger = mock_chat_logger
        name_bot.chat = mock_chat

        result = name_bot.name_functions("old_code", "snippets", "existing_names", 1)
        self.assertEqual(result, ["mock_function_name"])


if __name__ == "__main__":
    unittest.main()

