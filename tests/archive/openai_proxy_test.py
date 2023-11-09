import pytest
from unittest.mock import patch, MagicMock
from sweepai.utils.openai_proxy import OpenAIProxy, OPENAI_EXCLUSIVE_MODELS, OPENAI_API_KEY, OPENAI_API_TYPE, OPENAI_API_ENGINE_GPT35, OPENAI_API_ENGINE_GPT4, OPENAI_API_ENGINE_GPT4_32K, MULTI_REGION_CONFIG, AZURE_API_KEY


@patch('sweepai.utils.openai_proxy.openai')
@patch('sweepai.utils.openai_proxy.logger')
def test_call_openai_gpt35(mock_logger, mock_openai):
    proxy = OpenAIProxy()
    model = "gpt-3.5-turbo-16k"
    OPENAI_API_TYPE = None
    OPENAI_API_ENGINE_GPT35 = "gpt-3.5-turbo-16k"
    mock_openai.ChatCompletion.create.return_value = {"choices": [{"message": {"content": "test"}}]}
    assert proxy.call_openai(model, [], 10, 0.5) == "test"
    mock_logger.info.assert_called_once_with(f"Calling {model} with OpenAI.")