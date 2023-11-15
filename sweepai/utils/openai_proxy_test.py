import unittest
from unittest.mock import MagicMock, patch
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxy(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()
        self.mock_response = MagicMock()
        self.mock_response["choices"][0].message.content = "mocked content"
        self.model = "gpt-3.5-turbo-16k"
        self.messages = [{"role": "system", "content": "You are a helpful assistant."}]
        self.max_tokens = 100
        self.temperature = 0.5

    @patch("openai.ChatCompletion.create")
    def test_call_openai(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            self.model, self.messages, self.max_tokens, self.temperature
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    @patch("sweepai.utils.openai_proxy.logger")
    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", new="not azure")
    @patch(
        "sweepai.utils.openai_proxy.OPENAI_EXCLUSIVE_MODELS", new=["gpt-3.5-turbo-16k"]
    )
    def test_call_openai_with_exclusive_model(self, mock_create, mock_logger):
        mock_create.return_value = self.mock_response
        with self.assertRaises(Exception) as context:
            self.openai_proxy.call_openai(
                self.model, self.messages, self.max_tokens, self.temperature
            )
        self.assertTrue("OpenAI exclusive model." in str(context.exception))

    @patch("openai.ChatCompletion.create")
    @patch("sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT35", new="not None")
    def test_call_openai_with_gpt35_model(self, mock_create):
        mock_create.return_value = self.mock_response
        self.model = "gpt-3.5-turbo-16k"
        result = self.openai_proxy.call_openai(
            self.model, self.messages, self.max_tokens, self.temperature
        )
        self.assertEqual(result, "mocked content")


if __name__ == "__main__":
    unittest.main()
