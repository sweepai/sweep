import unittest
from unittest.mock import MagicMock, patch

from sweepai.config.server import (OPENAI_API_ENGINE_GPT4,
                                   OPENAI_API_ENGINE_GPT4_32K,
                                   OPENAI_API_ENGINE_GPT35)
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxyCallOpenai(unittest.TestCase):
    def setUp(self):
        self.mock_response = MagicMock()
        self.mock_response["choices"] = [MagicMock()]
        self.mock_response["choices"][0].message = MagicMock()
        self.mock_response["choices"][0].message.content = "mock content"

        self.proxy = OpenAIProxy()

    @patch(
        "sweepai.utils.openai_proxy.OpenAIProxy.set_openai_default_api_parameters",
        return_value=mock_response,
    )
    @patch(
        "sweepai.utils.openai_proxy.OpenAIProxy.create_openai_chat_completion",
        return_value=mock_response,
    )
    @patch("sweepai.utils.openai_proxy.logger")
    def test_call_openai(
        self,
        mock_logger,
        mock_create_openai_chat_completion,
        mock_set_openai_default_api_parameters,
    ):
        model = "text-davinci-002"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 150
        temperature = 0.5

        result = self.proxy.call_openai(model, messages, max_tokens, temperature)

        self.assertEqual(result, "mock content")
        mock_set_openai_default_api_parameters.assert_called_once_with(
            model, messages, max_tokens, temperature
        )
        mock_create_openai_chat_completion.assert_called_once_with(
            None, model, messages, max_tokens, temperature
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", None)
    @patch(
        "sweepai.utils.openai_proxy.OpenAIProxy.determine_openai_engine",
        return_value=None,
    )
    def test_call_openai_when_api_type_or_engine_is_none(
        self, mock_determine_openai_engine
    ):
        model = "text-davinci-002"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 150
        temperature = 0.5

        result = self.proxy.call_openai(model, messages, max_tokens, temperature)

        self.assertEqual(result, "mock content")
        mock_set_openai_default_api_parameters.assert_called_once_with(
            model, messages, max_tokens, temperature
        )

    @patch("sweepai.utils.openai_proxy.MULTI_REGION_CONFIG", None)
    def test_call_openai_when_multi_region_config_is_none(self):
        model = "text-davinci-002"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 150
        temperature = 0.5

        result = self.proxy.call_openai(model, messages, max_tokens, temperature)

        self.assertEqual(result, "mock content")
        mock_create_openai_chat_completion.assert_called_once_with(
            None, model, messages, max_tokens, temperature
        )

    @patch(
        "sweepai.utils.openai_proxy.random.sample",
        return_value=[("region_url", "api_key")],
    )
    def test_call_openai_when_shuffled_multi_region_config_is_created(
        self, mock_random_sample
    ):
        model = "text-davinci-002"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 150
        temperature = 0.5

        result = self.proxy.call_openai(model, messages, max_tokens, temperature)

        self.assertEqual(result, "mock content")
        mock_create_openai_chat_completion.assert_called_once_with(
            None, model, messages, max_tokens, temperature
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_API_KEY", None)
    def test_call_openai_when_api_key_is_not_found(self):
        model = "text-davinci-002"
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        max_tokens = 150
        temperature = 0.5

        with self.assertRaises(Exception):
            self.proxy.call_openai(model, messages, max_tokens, temperature)


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
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("unknown_model"), None
        )

    @patch("sweepai.utils.openai_proxy.OPENAI_EXCLUSIVE_MODELS", ["test_model"])
    @patch("sweepai.utils.openai_proxy.OPENAI_API_TYPE", "not_azure")
    @patch("sweepai.utils.openai_proxy.logger")
    def test_determine_openai_engine_when_model_is_in_exclusive_models_and_api_type_is_not_azure(
        self, mock_logger
    ):
        result = self.openai_proxy.determine_openai_engine("test_model")

        self.assertIsNone(result)
        mock_logger.info.assert_called_once_with(
            "Calling OpenAI exclusive model. test_model"
        )


if __name__ == "__main__":
    unittest.main()
