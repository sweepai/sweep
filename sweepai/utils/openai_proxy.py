import random
from typing import List, Optional

import openai
from loguru import logger
from openai.api_resources.abstract.api_resource import APIResource

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
                response = self.set_openai_default_api_parameters(model, messages, max_tokens, temperature)
                return response["choices"][0].message.content
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
                openai.api_type = OPENAI_API_TYPE
                openai.api_base = OPENAI_API_BASE
                openai.api_version = OPENAI_API_VERSION
                openai.api_key = AZURE_API_KEY
                response = self.create_openai_chat_completion(engine, model, messages, max_tokens, temperature)
                return response["choices"][0].message.content
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
                    openai.api_key = api_key
                    openai.api_base = region_url
                    openai.api_version = OPENAI_API_VERSION
                    openai.api_type = OPENAI_API_TYPE
                    response = self.create_openai_chat_completion(engine, model, messages, max_tokens, temperature)
                    return response["choices"][0].message.content
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.exception(f"Error calling {region_url}: {e}")
            raise Exception("No Azure regions available")
        except SystemExit:
            raise SystemExit
        except Exception as e:
            if OPENAI_API_KEY:
                try:
                    response = self.set_openai_default_api_parameters(model, messages, max_tokens, temperature)
                    return response["choices"][0].message.content
                except SystemExit:
                    raise SystemExit
                except Exception as _e:
    def set_openai_default_api_parameters(self, model: str, messages: List[dict], max_tokens: int, temperature: float) -> APIResource:
        """
        Sets the default API parameters for OpenAI and creates a chat completion.
    
        Args:
            model (str): The model to use for the chat completion.
            messages (List[dict]): The messages to use for the chat completion.
            max_tokens (int): The maximum number of tokens to use for the chat completion.
            temperature (float): The temperature to use for the chat completion.
    
        Returns:
            APIResource: The response from the chat completion.
        """
        self.configure_default_openai_api_settings()
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=OPENAI_TIMEOUT,
            seed=SEED,
        )
        return response
    
    def configure_default_openai_api_settings(self) -> None:
        """
        Configures the default settings for the OpenAI API.
        """
        openai.api_key = OPENAI_API_KEY
        openai.api_base = "https://api.openai.com/v1"
        openai.api_version = None
        openai.api_type = "open_ai"
            raise e

    def validate_and_execute_single_region_call(self, model: str, engine: str, messages: List[dict], max_tokens: int, temperature: float, response: APIResource) -> APIResource:
        """
        Validates the MULTI_REGION_CONFIG and executes a single region call if valid.
    
        Args:
            model (str): The model to use for the call.
            engine (str): The engine to use for the call.
            messages (List[dict]): The messages to use for the call.
            max_tokens (int): The maximum number of tokens to use for the call.
            temperature (float): The temperature to use for the call.
            response (APIResource): The response object to use for the call.
    
        Returns:
            APIResource: The response from the call.
        """
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
            openai.api_type = OPENAI_API_TYPE
            openai.api_base = OPENAI_API_BASE
            openai.api_version = OPENAI_API_VERSION
            openai.api_key = AZURE_API_KEY
            response = self.create_openai_chat_completion(engine, model, messages, max_tokens, temperature)
        return response

    def execute_single_region_api_call(self, model: str, engine: str, messages: List[dict], max_tokens: int, temperature: float, response: APIResource) -> APIResource:
        """
        Executes a single region API call.

        Args:
            model (str): The model to use for the call.
            engine (str): The engine to use for the call.
            messages (List[dict]): The messages to use for the call.
            max_tokens (int): The maximum number of tokens to use for the call.
            temperature (float): The temperature to use for the call.
            response (APIResource): The response object to use for the call.

        Returns:
            APIResource: The response from the call.
        """
        response = self.validate_and_execute_single_region_call(model, engine, messages, max_tokens, temperature, response)
        return response

    def determine_openai_engine(self, model: str) -> Optional[str]:
        engine = None
        if model in OPENAI_EXCLUSIVE_MODELS and OPENAI_API_TYPE != "azure":
            logger.info(f"Calling OpenAI exclusive model. {model}")
            raise Exception("OpenAI exclusive model.")
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
        return engine

    def select_engine_for_gpt35_model(self, model: str) -> Optional[str]:
        """
        Selects the engine for the gpt-3.5 model.

        Args:
            model (str): The model to select the engine for.

        Returns:
            Optional[str]: The selected engine, or None if no engine is selected.
        """
        if (
            model == "gpt-3.5-turbo-16k"
            or model == "gpt-3.5-turbo-16k-0613"
            and OPENAI_API_ENGINE_GPT35 is not None
        ):
            engine = OPENAI_API_ENGINE_GPT35

    def create_openai_chat_completion(self, engine: str, model: str, messages: List[dict], max_tokens: int, temperature: float) -> APIResource:
        """
        Creates a chat completion with OpenAI.

        Args:
            engine (str): The engine to use for the chat completion.
            model (str): The model to use for the chat completion.
            messages (List[dict]): The messages to use for the chat completion.
            max_tokens (int): The maximum number of tokens to use for the chat completion.
            temperature (float): The temperature to use for the chat completion.

        Returns:
            APIResource: The response from the chat completion.
        """
        response = openai.ChatCompletion.create(
            engine=engine,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=OPENAI_TIMEOUT,
        )
        return response

    def set_openai_default_api_parameters(self, model: str, messages: List[dict], max_tokens: int, temperature: float) -> APIResource:
        self.configure_default_openai_api_settings()
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=OPENAI_TIMEOUT,
            seed=SEED,
        )
        return response
    def configure_default_openai_api_settings(self):
        openai.api_key = OPENAI_API_KEY
        openai.api_base = "https://api.openai.com/v1"
        openai.api_version = None
        openai.api_type = "open_ai"
