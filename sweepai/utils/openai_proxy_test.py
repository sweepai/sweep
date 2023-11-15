import unittest
from unittest.mock import patch, MagicMock
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxy(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()
        self.mock_response = MagicMock()
        self.mock_response["choices"][0].message.content = "mocked content"

    @patch("openai.ChatCompletion.create")
    def test_call_openai(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            "gpt-3.5-turbo-16k",
            [{"role": "system", "content": "Hello, how can I assist you today?"}],
            100,
            0.5,
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_exclusive_model(self, mock_create):
        mock_create.return_value = self.mock_response
        with self.assertRaises(Exception) as context:
            self.openai_proxy.call_openai(
                "gpt-3.5-turbo-16k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
        self.assertTrue("OpenAI exclusive model." in str(context.exception))

    @patch("openai.ChatCompletion.create")
    def test_call_openai_gpt35_model(self, mock_create):
        mock_create.return_value = self.mock_response
        with patch.dict("os.environ", {"OPENAI_API_ENGINE_GPT35": "gpt-3.5-turbo-16k"}):
            result = self.openai_proxy.call_openai(
                "gpt-3.5-turbo-16k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
            self.assertEqual(result, "mocked content")


if __name__ == "__main__":
    unittest.main()
