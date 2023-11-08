from openai_proxy import OpenAIProxy

proxy = OpenAIProxy()

model = "gpt-4"

messages = [
    {"role": "system", "content": "You are an engineer"},
    {"role": "user", "content": "I am an engineer"},
]

out = proxy.call_openai(model, messages, 100, 0.1)
assert isinstance(out, str)

def test_call_openai():
    proxy = OpenAIProxy()

    model = "gpt-4"

    messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]

    out = proxy.call_openai(model, messages, 100, 0.1)
    assert isinstance(out, str)

def test_call_openai_with_different_models():
    proxy = OpenAIProxy()

    models = ["gpt-3.5-turbo-16k", "gpt-4", "gpt-4-32k"]

    messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]

    for model in models:
        out = proxy.call_openai(model, messages, 100, 0.1)
        assert isinstance(out, str)

def test_call_openai_exception_handling():
    proxy = OpenAIProxy()

    model = "gpt-4"

    messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]

    # Simulate SystemExit exception
    with pytest.raises(SystemExit):
        proxy.call_openai(model, messages, 100, 0.1)

    # Simulate general exception
    with pytest.raises(Exception):
        proxy.call_openai(model, messages, 100, 0.1)
