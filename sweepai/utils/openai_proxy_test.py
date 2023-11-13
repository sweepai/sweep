import unittest
from unittest.mock import patch, MagicMock
from sweepai.utils.openai_proxy import OpenAIProxy

import unittest
from unittest.mock import patch, MagicMock
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxy(unittest.TestCase):
    @patch("openai.ChatCompletion.create")
    def setUp(self, mock_create):
        self.mock_response = MagicMock()
        self.mock_response["choices"][0].message.content = "mocked content"
        mock_create.return_value = self.mock_response
        self.openai_proxy = OpenAIProxy()

    def test_call_openai(self):
        model = "gpt-3.5-turbo-16k"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        result = self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertEqual(result, "mocked content")


class TestOpenAIProxy(unittest.TestCase):
    @patch("openai.ChatCompletion.create")
    def setUp(self, mock_create):
        self.mock_response = MagicMock()
        self.mock_response["choices"][0].message.content = "mocked content"
        mock_create.return_value = self.mock_response
        self.openai_proxy = OpenAIProxy()

    def test_call_openai(self):
        model = "gpt-3.5-turbo-16k"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        result = self.openai_proxy.call_openai(model, messages, max_tokens, temperature)
        self.assertEqual(result, "mocked content")

        self.mock_response = MagicMock()
        self.mock_response["choices"][0].message.content = "mocked content"
        mock_create.return_value = self.mock_response
        self.openai_proxy = OpenAIProxy()

    def test_call_openai_exclusive_model(self):
        model = "exclusive_model"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 100
        temperature = 0.5
        with self.assertRaises(Exception):
            self.openai_proxy.call_openai(model, messages, max_tokens, temperature)

    # ... repeat for other test cases ...
