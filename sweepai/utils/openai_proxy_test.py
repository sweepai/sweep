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
    def test_call_openai_with_openai_exclusive_model(self, mock_create):
        with self.assertRaises(Exception):
            self.openai_proxy.call_openai(
                "gpt-3.5-turbo-16k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )

    @patch("openai.ChatCompletion.create")
    def test_call_openai_with_gpt35_model(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            "gpt-3.5-turbo-16k",
            [{"role": "system", "content": "Hello, how can I assist you today?"}],
            100,
            0.5,
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_with_gpt4_model(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            "gpt-4",
            [{"role": "system", "content": "Hello, how can I assist you today?"}],
            100,
            0.5,
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_with_gpt4_32k_model(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            "gpt-4-32k",
            [{"role": "system", "content": "Hello, how can I assist you today?"}],
            100,
            0.5,
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_with_no_api_type_or_engine(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            "gpt-3.5-turbo-16k",
            [{"role": "system", "content": "Hello, how can I assist you today?"}],
            100,
            0.5,
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_with_invalid_multi_region_config(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            "gpt-3.5-turbo-16k",
            [{"role": "system", "content": "Hello, how can I assist you today?"}],
            100,
            0.5,
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_with_valid_multi_region_config(self, mock_create):
        mock_create.return_value = self.mock_response
        result = self.openai_proxy.call_openai(
            "gpt-3.5-turbo-16k",
            [{"role": "system", "content": "Hello, how can I assist you today?"}],
            100,
            0.5,
        )
        self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_with_exception(self, mock_create):
        mock_create.side_effect = Exception("Test exception")
        with self.assertRaises(Exception):
            self.openai_proxy.call_openai(
                "gpt-3.5-turbo-16k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
