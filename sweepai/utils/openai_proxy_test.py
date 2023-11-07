from openai_proxy import OpenAIProxy

proxy = OpenAIProxy()

model = "gpt-3.5-turbo-1106"

messages = [
        {"role": "system", "content": "You are an engineer"},
        {"role": "user", "content": "I am an engineer"},
    ]

out = proxy.call_openai(model, messages, 100, 0.1)
assert isinstance(out, str)