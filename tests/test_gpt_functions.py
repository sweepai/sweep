import os
import openai

tests = """
# tests/test_fibonacci.py

from src.fibonacci import fibonacci

def test_fibonacci():
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(2) == 1
    assert fibonacci(3) == 2
    assert fibonacci(4) == 3
    assert fibonacci(5) == 5
    assert fibonacci(6) == 8
"""

prompt = f"""
{tests}

The above code is failing, can you help me debug? I also gave you some functions you can call.
"""

prompt = "Write a function to call the anthropic claude v1 model. Search google for the API reference."

functions = [
    # {
    #     "name": "cat",
    #     "description": "Cat the file.",
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "file_path": {
    #                 "type": "string",
    #             },
    #         }
    #     }
    # }
    {
        "name": "Google",
        "description": "Google search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                },
            }
        }
    }
]

response = openai.ChatCompletion.create(
    model="gpt-4-32k-0613",
    messages=[
        {
            "role": "system",
            "content": "You are a brilliant developers. Help the user with their problem."
        },
        {
            "role": "user",
            "content": prompt
        },
        # {
        #     "role": "assistant",
        #     "content": None,
        #     "function_call": {
        #         "name": "Google",
        #         "arguments": "{\"query\": \"Anthropic Claude v1 model API reference\"}"
        #     }
        # },
        # {
        #     "role": "function",
        #     "content": "Anthropic Claude v1 is a helpful and harmless LLM.",
        #     "name": "Google",
        # }
    ],
    functions=functions
)

print(dict(response.choices[0].message.function_call))

# from serpapi import GoogleSearch

# query = "anthropic claude v1 model API reference"
# query= "Leo DiCaprio girlfriend"
# GoogleSearch.SERP_API_KEY = os.environ.get("SERP_API_KEY")

# search = GoogleSearch({
#     "q": query, 
#     "location": "Austin,Texas",
#   })
# result = search.get_dict()
# print(result)



