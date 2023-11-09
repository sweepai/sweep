import pytest
from unittest.mock import patch
from openai_proxy import OpenAIProxy

proxy = OpenAIProxy()

def test_call_openai():
    model = "gpt-4"
    messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]
    with patch('openai.ChatCompletion.create') as mock_create:
        mock_create.return_value = {"choices": [{"message": {"content": "Test response"}}]}
        out = proxy.call_openai(model, messages, 100, 0.1)
        assert isinstance(out, str)
        assert out == "Test response"

def test_call_openai_different_model():
    model = "gpt-3.5-turbo-16k"
    messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]
    with patch('openai.ChatCompletion.create') as mock_create:
        mock_create.return_value = {"choices": [{"message": {"content": "Test response"}}]}
        out = proxy.call_openai(model, messages, 100, 0.1)
        assert isinstance(out, str)
        assert out == "Test response"

def test_call_openai_no_azure_regions():
    model = "gpt-4"
    messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]
    with patch('openai.ChatCompletion.create') as mock_create:
        mock_create.side_effect = Exception("No Azure regions available")
        with pytest.raises(Exception) as e:
            proxy.call_openai(model, messages, 100, 0.1)
        assert str(e.value) == "No Azure regions available"

def test_call_openai_no_openai_key():
    model = "gpt-4"
    messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]
    with patch('openai.ChatCompletion.create') as mock_create:
        mock_create.side_effect = Exception("OpenAI API Key not found and Azure Error")
        with pytest.raises(Exception) as e:
            proxy.call_openai(model, messages, 100, 0.1)
        assert str(e.value) == "OpenAI API Key not found and Azure Error"
