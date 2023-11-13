import pytest
from unittest.mock import patch
from openai_proxy import OpenAIProxy, OPENAI_EXCLUSIVE_MODELS, OPENAI_API_TYPE, OPENAI_API_ENGINE_GPT35, OPENAI_API_ENGINE_GPT4, OPENAI_API_ENGINE_GPT4_32K, MULTI_REGION_CONFIG

proxy = OpenAIProxy()

messages = [
    {"role": "system", "content": "You are an engineer"},
    {"role": "user", "content": "I am an engineer"},
]

def test_call_openai_exclusive_model():
    model = OPENAI_EXCLUSIVE_MODELS[0]
    with pytest.raises(Exception):
        proxy.call_openai(model, messages, 100, 0.1)

def test_call_openai_gpt35():
    model = "gpt-3.5-turbo-16k"
    with patch('openai.ChatCompletion.create') as mock_create:
        proxy.call_openai(model, messages, 100, 0.1)
    mock_create.assert_called_with(
        model=model,
        messages=messages,
        max_tokens=100,
        temperature=0.1,
        timeout=60,
        seed=100,
    )

def test_call_openai_gpt4():
    model = "gpt-4"
    with patch('openai.ChatCompletion.create') as mock_create:
        proxy.call_openai(model, messages, 100, 0.1)
    mock_create.assert_called_with(
        model=model,
        messages=messages,
        max_tokens=100,
        temperature=0.1,
        timeout=60,
        seed=100,
    )

def test_call_openai_gpt4_32k():
    model = "gpt-4-32k"
    with patch('openai.ChatCompletion.create') as mock_create:
        proxy.call_openai(model, messages, 100, 0.1)
    mock_create.assert_called_with(
        model=model,
        messages=messages,
        max_tokens=100,
        temperature=0.1,
        timeout=60,
        seed=100,
    )

def test_call_openai_no_api_type_or_engine():
    model = "gpt-4"
    with patch('openai.ChatCompletion.create') as mock_create:
        proxy.call_openai(model, messages, 100, 0.1)
    mock_create.assert_called_with(
        model=model,
        messages=messages,
        max_tokens=100,
        temperature=0.1,
        timeout=60,
        seed=100,
    )

def test_call_openai_invalid_multi_region_config():
    model = "gpt-4"
    with patch('openai.ChatCompletion.create') as mock_create:
        proxy.call_openai(model, messages, 100, 0.1)
    mock_create.assert_called_with(
        model=model,
        messages=messages,
        max_tokens=100,
        temperature=0.1,
        timeout=60,
        seed=100,
    )

def test_call_openai_valid_multi_region_config():
    model = "gpt-4"
    with patch('openai.ChatCompletion.create') as mock_create:
        proxy.call_openai(model, messages, 100, 0.1)
    mock_create.assert_called_with(
        model=model,
        messages=messages,
        max_tokens=100,
        temperature=0.1,
        timeout=60,
        seed=100,
    )
