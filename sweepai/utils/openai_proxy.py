import random

from loguru import logger
from openai import AzureOpenAI, OpenAI

from sweepai.config.server import (
    AZURE_API_KEY,
    BASERUN_API_KEY,
    MULTI_REGION_CONFIG,
    OPENAI_API_BASE,
    OPENAI_API_ENGINE_GPT4,
    OPENAI_API_ENGINE_GPT4_32K,
    OPENAI_API_ENGINE_GPT35,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
    OPENAI_API_VERSION,
)
from sweepai.logn.cache import file_cache

if BASERUN_API_KEY is not None:
    pass

OPENAI_TIMEOUT = 60  # one minute

OPENAI_EXCLUSIVE_MODELS = [
    "gpt-4-1106-preview",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-1106",
]
SEED = 100


class OpenAIProxy:
    @file_cache(ignore_params=[])
    def call_openai(self, model, messages, max_tokens, temperature) -> str:
        try:
            engine = self.determine_openai_engine(model)
            if OPENAI_API_TYPE is None or engine is None:
                response = self.set_openai_default_api_parameters(
                    model, messages, max_tokens, temperature
                )
                return response.choices[0].message.content
            # validity checks for MULTI_REGION_CONFIG
            if (
                MULTI_REGION_CONFIG is None
                or not isinstance(MULTI_REGION_CONFIG, list)
                or len(MULTI_REGION_CONFIG) == 0
                or not isinstance(MULTI_REGION_CONFIG[0], list)
            ):
                logger.info(
                    f"Calling {model} with engine {engine} on Azure url {OPENAI_API_BASE}."
                )
                response = self.create_openai_chat_completion(
                    engine,
                    OPENAI_API_BASE,
                    AZURE_API_KEY,
                    model,
                    messages,
                    max_tokens,
                    temperature,
                )
                return response.choices[0].message.content
            # multi region config is a list of tuples of (region_url, api_key)
            # we will try each region in order until we get a response
            # randomize the order of the list
            SHUFFLED_MULTI_REGION_CONFIG = random.sample(
                MULTI_REGION_CONFIG, len(MULTI_REGION_CONFIG)
            )
            for region_url, api_key in SHUFFLED_MULTI_REGION_CONFIG:
                try:
                    logger.info(
                        f"Calling {model} with engine {engine} on Azure url {region_url}."
                    )
                    response = self.create_openai_chat_completion(
                        engine,
                        region_url,
                        api_key,
                        model,
                        messages,
                        max_tokens,
                        temperature,
                    )
                    return response.choices[0].message.content
                except Exception as e:
                    logger.exception(f"Error calling {region_url}: {e}")
            raise Exception("No Azure regions available")
        except SystemExit:
            raise SystemExit
        except Exception as e:
            if OPENAI_API_KEY:
                try:
                    response = self.set_openai_default_api_parameters(
                        model, messages, max_tokens, temperature
                    )
                    return response.choices[0].message.content
                except SystemExit:
                    raise SystemExit
                except Exception as _e:
                    logger.error(f"OpenAI API Key found but error: {_e}")
            logger.error(f"OpenAI API Key not found and Azure Error: {e}")
            # Raise exception to report error
            raise e

    def determine_openai_engine(self, model):
        engine = None
        if model in OPENAI_EXCLUSIVE_MODELS and OPENAI_API_TYPE != "azure":
            logger.info(f"Calling OpenAI exclusive model. {model}")
        elif (
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
        return engine

    def create_openai_chat_completion(
        self, engine, base_url, api_key, model, messages, max_tokens, temperature
    ):
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=base_url,
            api_version=OPENAI_API_VERSION,
        )
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=OPENAI_TIMEOUT,
        )
        return response

    def set_openai_default_api_parameters(
        self, model, messages, max_tokens, temperature
    ):
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=OPENAI_TIMEOUT,
            seed=SEED,
        )
        return response
