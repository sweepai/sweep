import unittest
from unittest.mock import MagicMock, patch

from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxy(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()

    def test_call_openai(self, mock_create):
        mock_response = MagicMock()
        mock_response["choices"] = [MagicMock()]
        mock_response["choices"][0].message = MagicMock()
        mock_response["choices"][0].message.content = "mocked content"
        model = "gpt-3.5-turbo-16k"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        with patch("openai.ChatCompletion.create", return_value=mock_response):
            result = self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertEqual(result, mock_response["choices"][0].message.content)

    @patch("sweepai.utils.openai_proxy.OPENAI_API_KEY", None)
    @patch("sweepai.utils.openai_proxy.logger", MagicMock())
    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", "not_azure")
    @patch("sweepai.utils.openai_proxy.OPENAI_EXCLUSIVE_MODELS", ["gpt-3.5-turbo-16k"])
    @patch("openai.ChatCompletion.create", return_value=MagicMock())
    def test_call_openai_with_exclusive_model_and_not_azure(self, mock_create):
        model = "gpt-3.5-turbo-16k"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        with self.assertRaises(Exception) as context:
            self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertTrue("OpenAI exclusive model." in str(context.exception))

    def test_call_openai_with_gpt35_and_api_type_none(self, mock_create):
        model = "gpt-3.5-turbo-16k"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        with patch("sweepai.utils.openai_proxy.OPENAI_API_KEY", None), patch("sweepai.utils.openai_proxy.logger", MagicMock()), patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", None), patch("sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT35", "gpt-3.5-turbo-16k"), patch("openai.ChatCompletion.create", return_value=mock_response):
            result = self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertEqual(result, mock_response["choices"][0].message.content)
        mock_response = MagicMock()
        mock_response["choices"] = [MagicMock()]
        mock_response["choices"][0].message = MagicMock()
        mock_response["choices"][0].message.content = "mocked content"
        model = "gpt-3.5-turbo-16k"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        result = self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertEqual(result, self.mock_response["choices"][0].message.content)

    def test_call_openai_with_gpt4_and_api_type_none(self, mock_create):
        model = "gpt-4"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        with patch("sweepai.utils.openai_proxy.OPENAI_API_KEY", None), patch("sweepai.utils.openai_proxy.logger", MagicMock()), patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", None), patch("sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT4", "gpt-4"), patch("openai.ChatCompletion.create", return_value=mock_response):
            result = self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertEqual(result, mock_response["choices"][0].message.content)


if __name__ == "__main__":
    unittest.main()
        mock_response = MagicMock()
        mock_response["choices"] = [MagicMock()]
        mock_response["choices"][0].message = MagicMock()
        mock_response["choices"][0].message.content = "mocked content"
        model = "gpt-4"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        result = self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertEqual(result, self.mock_response["choices"][0].message.content)

if __name__ == "__main__":
    unittest.main()
