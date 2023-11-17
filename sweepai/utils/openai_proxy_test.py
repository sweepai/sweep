import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from sweepai.config.server import (OPENAI_API_ENGINE_GPT4,
                                   OPENAI_API_ENGINE_GPT4_32K,
                                   OPENAI_API_ENGINE_GPT35)
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxyDetermineOpenaiEngine(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()

    def test_determine_openai_engine(self):
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-3.5-turbo-16k"),
            OPENAI_API_ENGINE_GPT35,
        )
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-4"), OPENAI_API_ENGINE_GPT4
        )
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-4-32k"),
            OPENAI_API_ENGINE_GPT4_32K,
        )
        self.assertIsNone(self.openai_proxy.determine_openai_engine("unknown_model"))

    @mock.patch(
        "sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT35", "test_engine_gpt35"
    )
    def test_determine_openai_engine_gpt35(self):
        openai_proxy = OpenAIProxy()
        result = openai_proxy.determine_openai_engine("gpt-3.5-turbo-16k")
        self.assertEqual(result, "test_engine_gpt35")

    @mock.patch("sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT4", "test_engine_gpt4")
    def test_determine_openai_engine_gpt4(self):
        openai_proxy = OpenAIProxy()
        result = openai_proxy.determine_openai_engine("gpt-4")
        self.assertEqual(result, "test_engine_gpt4")

    @mock.patch(
        "sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT4_32K", "test_engine_gpt4_32k"
    )
    def test_determine_openai_engine_gpt4_32k(self):
        openai_proxy = OpenAIProxy()
        result = openai_proxy.determine_openai_engine("gpt-4-32k")
        self.assertEqual(result, "test_engine_gpt4_32k")

    def test_determine_openai_engine_unknown_model(self):
        openai_proxy = OpenAIProxy()
        result = openai_proxy.determine_openai_engine("unknown_model")
        self.assertIsNone(result)


class TestOpenAIProxyCallOpenai(unittest.TestCase):
    def setUp(self):
        self.mock_response = MagicMock()
        self.mock_response["choices"][0].message.content = "mock content"

        self.mock_openai = MagicMock()
        type(self.mock_openai).api_key = PropertyMock(return_value="mock_api_key")
        type(self.mock_openai).api_base = PropertyMock(return_value="mock_api_base")
        type(self.mock_openai).api_version = PropertyMock(
            return_value="mock_api_version"
        )
        type(self.mock_openai).api_type = PropertyMock(return_value="mock_api_type")

        self.proxy = OpenAIProxy()

    @patch("sweepai.utils.openai_proxy.OpenAIProxy.set_openai_default_api_parameters")
    @patch("sweepai.utils.openai_proxy.OpenAIProxy.create_openai_chat_completion")
    @patch("sweepai.utils.openai_proxy.openai", new=self.mock_openai)
    def test_call_openai(self, mock_set_default_params, mock_create_chat_completion):
        mock_set_default_params.return_value = self.mock_response
        mock_create_chat_completion.return_value = self.mock_response

        result = self.proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")

        openai_proxy = OpenAIProxy()
        result = openai_proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")
        mock_set_default_params.assert_called_once_with(
            "model", "messages", "max_tokens", "temperature"
        )
        mock_logger_error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
