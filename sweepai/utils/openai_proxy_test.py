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

    @patch("openai.ChatCompletion.create")
    def test_call_openai_gpt4_model(self, mock_create):
        mock_create.return_value = self.mock_response
        with patch.dict("os.environ", {"OPENAI_API_ENGINE_GPT4": "gpt-4"}):
            result = self.openai_proxy.call_openai(
                "gpt-4",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
            self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_gpt4_32k_model(self, mock_create):
        mock_create.return_value = self.mock_response
        with patch.dict("os.environ", {"OPENAI_API_ENGINE_GPT4_32K": "gpt-4-32k"}):
            result = self.openai_proxy.call_openai(
                "gpt-4-32k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
            self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_no_api_type_or_engine(self, mock_create):
        mock_create.return_value = self.mock_response
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test_key"}):
            result = self.openai_proxy.call_openai(
                "gpt-4-32k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
            self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_invalid_multi_region_config(self, mock_create):
        mock_create.return_value = self.mock_response
        with patch.dict(
            "os.environ",
            {
                "AZURE_API_KEY": "test_key",
                "OPENAI_API_BASE": "https://api.openai.com/v1",
                "OPENAI_API_VERSION": "v1",
                "OPENAI_API_TYPE": "azure",
            },
        ):
            result = self.openai_proxy.call_openai(
                "gpt-4-32k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
            self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_multi_region_config(self, mock_create):
        mock_create.side_effect = [
            Exception("Error calling region"),
            self.mock_response,
        ]
        with patch.dict(
            "os.environ",
            {
                "AZURE_API_KEY": "test_key",
                "OPENAI_API_BASE": "https://api.openai.com/v1",
                "OPENAI_API_VERSION": "v1",
                "OPENAI_API_TYPE": "azure",
            },
        ):
            self.openai_proxy.MULTI_REGION_CONFIG = [
                ("region1", "key1"),
                ("region2", "key2"),
            ]
            result = self.openai_proxy.call_openai(
                "gpt-4-32k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
            self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_no_regions_available(self, mock_create):
        mock_create.side_effect = Exception("Error calling region")
        with patch.dict(
            "os.environ",
            {
                "AZURE_API_KEY": "test_key",
                "OPENAI_API_BASE": "https://api.openai.com/v1",
                "OPENAI_API_VERSION": "v1",
                "OPENAI_API_TYPE": "azure",
            },
        ):
            self.openai_proxy.MULTI_REGION_CONFIG = [
                ("region1", "key1"),
                ("region2", "key2"),
            ]
            with self.assertRaises(Exception) as context:
                self.openai_proxy.call_openai(
                    "gpt-4-32k",
                    [
                        {
                            "role": "system",
                            "content": "Hello, how can I assist you today?",
                        }
                    ],
                    100,
                    0.5,
                )
            self.assertTrue("No Azure regions available" in str(context.exception))

    @patch("openai.ChatCompletion.create")
    def test_call_openai_exception_handling(self, mock_create):
        mock_create.side_effect = [
            Exception("Error calling region"),
            self.mock_response,
        ]
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test_key"}):
            result = self.openai_proxy.call_openai(
                "gpt-4-32k",
                [{"role": "system", "content": "Hello, how can I assist you today?"}],
                100,
                0.5,
            )
            self.assertEqual(result, "mocked content")

    @patch("openai.ChatCompletion.create")
    def test_call_openai_exception_handling_no_api_key(self, mock_create):
        mock_create.side_effect = Exception("Error calling region")
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            with self.assertRaises(Exception) as context:
                self.openai_proxy.call_openai(
                    "gpt-4-32k",
                    [
                        {
                            "role": "system",
                            "content": "Hello, how can I assist you today?",
                        }
                    ],
                    100,
                    0.5,
                )
            self.assertTrue("Error calling region" in str(context.exception))


if __name__ == "__main__":
    unittest.main()
