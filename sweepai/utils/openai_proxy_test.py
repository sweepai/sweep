import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from sweepai.config.server import (OPENAI_API_ENGINE_GPT4,
                                   OPENAI_API_ENGINE_GPT4_32K,
                                   OPENAI_API_ENGINE_GPT35)
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxyCallOpenai(unittest.TestCase):
    def setUp(self):
        self.proxy = OpenAIProxy()
        self.mock_response = MagicMock()
        self.mock_response["choices"][0].message.content = "mock content"

        self.mock_openai = MagicMock()
        type(self.mock_openai).api_key = PropertyMock(return_value="mock_api_key")
        type(self.mock_openai).api_base = PropertyMock(return_value="mock_api_base")
        type(self.mock_openai).api_version = PropertyMock(
            return_value="mock_api_version"
        )
        type(self.mock_openai).api_type = PropertyMock(return_value="mock_api_type")

        self.mock_logger = MagicMock()
        self.mock_random = MagicMock()

    @patch("sweepai.utils.openai_proxy.openai", new_callable=PropertyMock)
    @patch("sweepai.utils.openai_proxy.logger", new_callable=PropertyMock)
    @patch("sweepai.utils.openai_proxy.random", new_callable=PropertyMock)
    @patch("sweepai.utils.openai_proxy.OpenAIProxy.set_openai_default_api_parameters")
    @patch("sweepai.utils.openai_proxy.OpenAIProxy.create_openai_chat_completion")
    def test_call_openai(
        self,
        mock_set_openai_default_api_parameters,
        mock_create_openai_chat_completion,
        mock_openai,
        mock_logger,
        mock_random,
    ):
        mock_set_openai_default_api_parameters.return_value = self.mock_response
        mock_create_openai_chat_completion.return_value = self.mock_response
        mock_openai.return_value = self.mock_openai
        mock_logger.return_value = self.mock_logger
        mock_random.return_value = self.mock_random

        result = self.proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")

    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", None)
    @patch(
        "sweepai.utils.openai_proxy.OpenAIProxy.determine_openai_engine",
        return_value=None,
    )
    def test_call_openai_when_api_type_or_engine_is_none(
        self, mock_determine_openai_engine, mock_api_type
    ):
        result = self.proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")
        mock_determine_openai_engine.assert_called_once_with("model")
        self.mock_set_openai_default_api_parameters.assert_called_once_with(
            "model", "messages", "max_tokens", "temperature"
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", "api_type")
    @patch(
        "sweepai.utils.openai_proxy.OpenAIProxy.determine_openai_engine",
        return_value="engine",
    )
    @patch("sweepai.utils.openai_proxy.MULTI_REGION_CONFIG", None)
    def test_call_openai_when_multi_region_config_is_none(
        self, mock_determine_openai_engine, mock_api_type, mock_multi_region_config, mock_create_openai_chat_completion
    ):
        result = self.proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")
        mock_determine_openai_engine.assert_called_once_with("model")
        mock_create_openai_chat_completion.assert_called_once_with(
            "engine", "model", "messages", "max_tokens", "temperature"
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_KEY", None)
    def test_call_openai_when_openai_api_key_is_none(self, mock_openai_api_key):
        with self.assertRaises(Exception):
            self.proxy.call_openai("model", "messages", "max_tokens", "temperature")
        self.mock_logger.error.assert_called_with(
            "OpenAI API Key not found and Azure Error: mock_api_key"
        )


class TestOpenAIProxyDetermineOpenaiEngine(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()

    def test_determine_openai_engine(self):
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-3.5-turbo-16k"),
            OPENAI_API_ENGINE_GPT35,
        )
        self.assertEqual(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")
        mock_determine_openai_engine.assert_called_once_with("model")
        mock_set_openai_default_api_parameters.assert_called_once_with(
            "model", "messages", "max_tokens", "temperature"
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", "api_type")
    @patch(
        "sweepai.utils.openai_proxy.OpenAIProxy.determine_openai_engine",
        return_value="engine",
    )
    @patch("sweepai.utils.openai_proxy.MULTI_REGION_CONFIG", None)
    def test_call_openai_when_multi_region_config_is_none(
        self, mock_determine_openai_engine, mock_api_type, mock_multi_region_config
    ):
        result = self.proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")
        mock_determine_openai_engine.assert_called_once_with("model")
        self.mock_create_openai_chat_completion.assert_called_once_with(
            "engine", "model", "messages", "max_tokens", "temperature"
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_KEY", None)
    def test_call_openai_when_openai_api_key_is_none(self, mock_openai_api_key):
        with self.assertRaises(Exception):
            self.proxy.call_openai("model", "messages", "max_tokens", "temperature")
        self.mock_logger.error.assert_called_with(
            "OpenAI API Key not found and Azure Error: mock_api_key"
        )


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
        self.assertEqual(self.openai_proxy.determine_openai_engine("other"), None)

    @patch("sweepai.utils.openai_proxy.OPENAI_EXCLUSIVE_MODELS", ["exclusive_model"])
    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", "not_azure")
    @patch("sweepai.utils.openai_proxy.logger")
    def test_determine_openai_engine_when_model_is_exclusive_and_api_type_is_not_azure(
        self, mock_logger, mock_api_type, mock_exclusive_models
    ):
        result = self.openai_proxy.determine_openai_engine("exclusive_model")
        self.assertEqual(result, None)
        mock_logger.info.assert_called_once_with(
            "Calling OpenAI exclusive model. exclusive_model"
        )


if __name__ == "__main__":
    unittest.main()
if __name__ == "__main__":
    unittest.main()
