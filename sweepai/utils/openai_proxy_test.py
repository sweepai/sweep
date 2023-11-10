import unittest
from unittest.mock import patch, MagicMock
from openai_proxy import OpenAIProxy

class TestOpenAIProxy(unittest.TestCase):
    def setUp(self):
        self.proxy = OpenAIProxy()
        self.model = "gpt-4"
        self.messages = [
            {"role": "system", "content": "You are an engineer"},
            {"role": "user", "content": "I am an engineer"},
        ]
        self.max_tokens = 100
        self.temperature = 0.1

    @patch('openai.ChatCompletion.create')
    def test_call_openai(self, mock_create):
        mock_create.return_value = {'choices': [{'message': {'content': 'Test content'}}]}
        out = self.proxy.call_openai(self.model, self.messages, self.max_tokens, self.temperature)
        self.assertIsInstance(out, str)
        mock_create.assert_called_once()

    @patch('openai.ChatCompletion.create')
    def test_call_openai_with_custom_engine(self, mock_create):
        mock_create.return_value = {'choices': [{'message': {'content': 'Test content'}}]}
        out = self.proxy.call_openai_with_custom_engine('engine', self.model, self.messages, self.max_tokens, self.temperature)
        self.assertIsInstance(out, str)
        mock_create.assert_called_once()

    @patch('openai.ChatCompletion.create')
    def test_call_openai_with_default_settings(self, mock_create):
        mock_create.return_value = {'choices': [{'message': {'content': 'Test content'}}]}
        out = self.proxy.call_openai_with_default_settings(self.model, self.messages, self.max_tokens, self.temperature)
        self.assertIsInstance(out, str)
        mock_create.assert_called_once()

if __name__ == '__main__':
    unittest.main()
