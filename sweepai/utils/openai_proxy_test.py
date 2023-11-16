import unittest
from unittest.mock import MagicMock, patch

from sweepai.config.server import (OPENAI_API_ENGINE_GPT4,
                                   OPENAI_API_ENGINE_GPT4_32K,
                                   OPENAI_API_ENGINE_GPT35)
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxyDetermineOpenaiEngine(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()

    def test_determine_openai_engine(self):
        self.assertIsNone(self.openai_proxy.determine_openai_engine("unknown_model"))
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

    @patch("sweepai.utils.openai_proxy.OPENAI_EXCLUSIVE_MODELS", ["exclusive_model"])
    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", "not_azure")
    def test_determine_openai_engine_raises_exception(self):
        with self.assertRaises(Exception):
            self.openai_proxy.determine_openai_engine("exclusive_model")

    @patch("sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT35", "gpt35_engine")
    def test_determine_openai_engine_gpt35(self):
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-3.5-turbo-16k"),
            "gpt35_engine",
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT4", "gpt4_engine")
    def test_determine_openai_engine_gpt4(self):
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-4"), "gpt4_engine"
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_ENGINE_GPT4_32K", "gpt4_32k_engine")
    def test_determine_openai_engine_gpt4_32k(self):
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-4-32k"), "gpt4_32k_engine"
        )


class TestOpenAIProxyCallOpenai(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()
        self.mock_response = MagicMock()
        self.mock_response["choices"] = [MagicMock()]
        self.mock_response["choices"][0].message.content = "mock content"

    @patch("sweepai.utils.openai_proxy.OpenAIProxy.set_openai_default_api_parameters")
    @patch("sweepai.utils.openai_proxy.OpenAIProxy.create_openai_chat_completion")
    @patch("sweepai.utils.openai_proxy.openai")
    @patch("sweepai.utils.openai_proxy.logger")
    @patch("sweepai.utils.openai_proxy.random.sample")
    def test_call_openai(
        self,
        mock_random_sample,
        mock_logger,
        mock_openai,
        mock_create_openai_chat_completion,
        mock_set_openai_default_api_parameters,
    ):
        mock_set_openai_default_api_parameters.return_value = self.mock_response
        mock_create_openai_chat_completion.return_value = self.mock_response
        mock_random_sample.return_value = [("region_url", "api_key")]

        result = self.openai_proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")

    @patch("sweepai.utils.openai_proxy.OpenAIProxy.set_openai_default_api_parameters")
    @patch("sweepai.utils.openai_proxy.OpenAIProxy.determine_openai_engine")
    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", None)
    def test_call_openai_api_type_none(
        self, mock_determine_openai_engine, mock_set_openai_default_api_parameters
    ):
        mock_set_openai_default_api_parameters.return_value = self.mock_response
        mock_determine_openai_engine.return_value = "engine"

        result = self.openai_proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")

    @patch("sweepai.utils.openai_proxy.OpenAIProxy.set_openai_default_api_parameters")
    @patch("sweepai.utils.openai_proxy.OpenAIProxy.determine_openai_engine")
    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", "api_type")
    def test_call_openai_engine_none(
        self, mock_determine_openai_engine, mock_set_openai_default_api_parameters
    ):
        mock_set_openai_default_api_parameters.return_value = self.mock_response
        mock_determine_openai_engine.return_value = None

        result = self.openai_proxy.call_openai(
            "model", "messages", "max_tokens", "temperature"
        )
        self.assertEqual(result, "mock content")


if __name__ == "__main__":
    unittest.main()
if __name__ == "__main__":
    unittest.main()
