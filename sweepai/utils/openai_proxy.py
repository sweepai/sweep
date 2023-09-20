import os
import traceback as tb
from logn import logger, file_cache
import openai
from sweepai.config.server import (
    AZURE_API_KEY,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
    OPENAI_API_BASE,
    OPENAI_API_VERSION,
    OPENAI_API_ENGINE_GPT35,
    OPENAI_API_ENGINE_GPT4,
    OPENAI_API_ENGINE_GPT4_32K,
)


class OpenAIProxy:
    def __init__(self):
        pass

    @file_cache(ignore_params=["max_tokens"])
    def call_openai(self, model, messages, max_tokens, temperature):
        try:
            engine = None
            if (
                model == "gpt-3.5-turbo-16k"
                or model == "gpt-3.5-turbo-16k-0613"
                and OPENAI_API_ENGINE_GPT35 is not None
            ):
                engine = OPENAI_API_ENGINE_GPT35
            elif (
                model == "gpt-4"
                or model == "gpt-4-0613"
                and OPENAI_API_ENGINE_GPT4 is not None
            ):
                engine = OPENAI_API_ENGINE_GPT4
            elif (
                model == "gpt-4-32k"
                or model == "gpt-4-32k-0613"
                and OPENAI_API_ENGINE_GPT4_32K is not None
            ):
                engine = OPENAI_API_ENGINE_GPT4_32K
            if OPENAI_API_TYPE is None or engine is None:
                openai.api_key = OPENAI_API_KEY
                openai.api_base = "https://api.openai.com/v1"
                openai.api_version = None
                openai.api_type = "open_ai"
                logger.info(f"Calling {model} on OpenAI.")
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response["choices"][0].message.content
            logger.info(
                f"Calling {model} with engine {engine} on Azure url {OPENAI_API_BASE}."
            )
            openai.api_type = OPENAI_API_TYPE
            openai.api_base = OPENAI_API_BASE
            openai.api_version = OPENAI_API_VERSION
            openai.api_key = AZURE_API_KEY
            response = openai.ChatCompletion.create(
                engine=engine,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response["choices"][0].message.content
        except SystemExit:
            raise SystemExit
        except Exception as e:
            if OPENAI_API_KEY:
                try:
                    openai.api_key = OPENAI_API_KEY
                    openai.api_base = "https://api.openai.com/v1"
                    openai.api_version = None
                    openai.api_type = "open_ai"
                    logger.info(f"Calling {model} with OpenAI.")
                    response = openai.ChatCompletion.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return response["choices"][0].message.content
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.error(f"OpenAI API Key found but error: {e}")
            logger.error(f"OpenAI API Key not found and Azure Error: {e}")
