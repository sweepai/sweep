import os
from loguru import logger
import openai
from sweepai.config.server import AZURE_API_KEY, OPENAI_API_KEY, OPENAI_API_TYPE, OPENAI_API_BASE, OPENAI_API_VERSION, OPENAI_API_ENGINE_GPT35, OPENAI_API_ENGINE_GPT4, OPENAI_API_ENGINE_GPT4_32K

class OpenAIProxy:
    def __init__(self):
        pass

    def call_openai(self, model, messages, max_tokens, temperature):
        try:
            if OPENAI_API_TYPE != "azure":
                openai.api_key = OPENAI_API_KEY
                logger.info(f"Calling {model} on OpenAI.")
                response = openai.Completion.create(
                    model=model,
                    prompt=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response['choices'][0].message
            openai.api_type = OPENAI_API_TYPE
            openai.api_base = OPENAI_API_BASE
            openai.api_version = OPENAI_API_VERSION
            openai.api_key = AZURE_API_KEY
            if model == 'gpt-3.5-turbo-16k' or model == 'gpt-3.5-turbo-16k-0613'\
                and OPENAI_API_ENGINE_GPT35 is not None:
                engine = OPENAI_API_ENGINE_GPT35
            elif model == 'gpt-4' or model == 'gpt-4-0613'\
                and OPENAI_API_ENGINE_GPT4 is not None:
                engine = OPENAI_API_ENGINE_GPT4
            elif model == 'gpt-4-32k' or model == 'gpt-4-32k-0613'\
                and OPENAI_API_ENGINE_GPT4_32K is not None:
                engine = OPENAI_API_ENGINE_GPT4_32K
            logger.info(f"Calling {model} with engine {engine} on Azure.")
            response = openai.ChatCompletion.create(
                engine=engine,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            print(response)
            print(type(response))
            print(response['choices'])
            print(type(response['choices']))
            print(response['choices'][0])
            print(type(response['choices'][0]))
            print(response['choices'][0].message)
            print(type(response['choices'][0].message))
            print(response['choices'][0].message.content)
            print(type(response['choices'][0].message.content))
            import pdb; pdb.set_trace()
            return response['choices'][0].message.content
        except Exception as e:
            if OPENAI_API_KEY:
                openai.api_key = OPENAI_API_KEY
                logger.info(f"Azure failed, calling {model} with engine {engine} on OpenAI.")
                response = openai.Completion.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response['choices'][0].message
            else:
                logger.error(f"OpenAI API Key not found and Azure Error: {e}")
                raise e
