import unittest
from unittest.mock import MagicMock, PropertyMock, patch


from sweepai.config.server import OPENAI_API_ENGINE_GPT35
from sweepai.utils.openai_proxy import OpenAIProxy


class TestOpenAIProxyCallOpenai(unittest.TestCase):
    @unittest.skip("Breaks")
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

        proxy = OpenAIProxy()
        result = proxy.call_openai("model", "messages", "max_tokens", "temperature")
        self.assertEqual(result, "mock content")


class TestOpenAIProxyDetermineOpenaiEngine(unittest.TestCase):
    def setUp(self):
        self.openai_proxy = OpenAIProxy()

    def test_determine_openai_engine(self):
        self.assertEqual(
            self.openai_proxy.determine_openai_engine("gpt-3.5-turbo-16k"),
            OPENAI_API_ENGINE_GPT35,
        )
        self.assertEqual(self.openai_proxy.determine_openai_engine("other"), None)


# class TestOpenAIProxy(unittest.TestCase):
#     @pytest.mark.skip("Breaks")
#     @patch(
#         "sweepai.utils.openai_proxy.MULTI_REGION_CONFIG",
#         new=[("url1", "api_key1"), ("url2", "api_key2")],
#     )
#     @patch("sweepai.utils.openai_proxy.AzureOpenAI")
#     @patch("sweepai.utils.openai_proxy.OpenAI")
#     def test_azure_fail_openai_success(self, mock_openai, mock_azure):
#         mock_azure_instance = MagicMock()
#         mock_azure.return_value = mock_azure_instance
#         mock_azure_instance.chat.completions.create.side_effect = APITimeoutError(
#             "Azure decides to be flaky."
#         )

#         mock_openai_instance = MagicMock()
#         mock_openai.return_value = mock_openai_instance
#         mock_openai_instance.chat.completions.create.return_value = (
#             "Successful response"
#         )

#         proxy = OpenAIProxy()

#         model = "gpt-4"
#         messages = [{"role": "system", "content": "Hello"}]
#         tools = []
#         max_tokens = 256
#         temperature = 0.0
#         seed = 0

#         response = proxy.call_openai(
#             model, messages, tools, max_tokens, temperature, seed
#         )

#         mock_azure_instance.chat.completions.create.assert_called()  # This checks that Azure API was called
#         mock_openai_instance.chat.completions.create.assert_called()  # This checks that OpenAI API was called
#         self.assertEqual(
#             response, "Successful response"
#         )  # This checks that the response is from OpenAI after Azure fails


if __name__ == "__main__":
    unittest.main() # these tests are broken
