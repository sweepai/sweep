from unittest.mock import patch

from sweepai.utils.openai_proxy import OpenAIProxy


@patch("sweepai.utils.openai_proxy.openai")
@patch("sweepai.utils.openai_proxy.logger")
def test_call_openai_gpt35(mock_logger, mock_openai):
    proxy = OpenAIProxy()
    model = "gpt-3.5-turbo-16k"
    mock_openai.ChatCompletion.create.return_value = {
        "choices": [{"message": {"content": "test"}}]
    }
    assert proxy.call_openai(model, [], 10, 0.5) == "test"
    mock_logger.info.assert_called_once_with(f"Calling {model} with OpenAI.")
