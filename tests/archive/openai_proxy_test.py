from sweepai.utils.openai_proxy import OpenAIProxy

openai_proxy = OpenAIProxy()
resp = openai_proxy.call_openai(
    model="gpt-3.5-turbo-16k-0613",
    messages=[{"role": "user", "content": "I am a human."}],
    max_tokens=100,
    temperature=0.5,
)

print(resp)
