import os
import random

import backoff
from loguru import logger
from openai import APITimeoutError, AzureOpenAI, InternalServerError, OpenAI, RateLimitError
from openai.types.chat.chat_completion import ChatCompletion

from sweepai.config.server import (
    AZURE_API_KEY,
    AZURE_OPENAI_DEPLOYMENT,
    DEFAULT_GPT4_MODEL,
    MULTI_REGION_CONFIG,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
    OPENAI_API_VERSION,
    OPENAI_EMBEDDINGS_API_TYPE,
    OPENAI_EMBEDDINGS_AZURE_API_VERSION,
    OPENAI_EMBEDDINGS_AZURE_DEPLOYMENT,
    OPENAI_EMBEDDINGS_AZURE_ENDPOINT,
)
from sweepai.core.entities import Message
from sweepai.logn.cache import file_cache
from sweepai.utils.timer import Timer
from anthropic import Anthropic

OPENAI_TIMEOUT = 120

OPENAI_EXCLUSIVE_MODELS = [
    "gpt-3.5-turbo-1106",
]
SEED = 100

RATE_LIMITS = {
    "australiaeast": 80000,
    "brazilsouth": 0,
    "canadaeast": 80000,
    "eastus": 80000,
    "eastus2": 80000,
    "francecentral": 80000,
    "japaneast": 0,
    "northcentralus": 80000,
    "norwayeast": 150000,
    "southafricanorth": 0,
    "southcentralus": 80000,
    "southindia": 150000,
    "swedencentral": 150000,
    "switzerlandnorth": 0,
    "uksouth": 80000,
    "westeurope": 0,
    "westus": 80000,
}


class OpenAIProxy:
    @file_cache(ignore_params=[])
    def call_openai(
        self,
        model: str,
        messages: list[Message],
        tools: list[str] = [],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stop_sequences: list[str] = [],
        seed: int = 0,
    ):
        try:
            engine = self.determine_openai_engine(model)
            if OPENAI_API_TYPE is None or engine is None:
                with Timer():
                    response = self.set_openai_default_api_parameters(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        tools=tools,
                    )
                    return response
            # validity checks for MULTI_REGION_CONFIG
            if (
                MULTI_REGION_CONFIG is None
                or not isinstance(MULTI_REGION_CONFIG, list)
                or len(MULTI_REGION_CONFIG) == 0
                or not isinstance(MULTI_REGION_CONFIG[0], list)
            ):
                if OPENAI_API_TYPE == "azure" or not OPENAI_API_KEY:
                    logger.info(
                        f"Calling {model} with engine {engine} on Azure url {OPENAI_API_BASE}."
                    )
                    try:
                        with Timer():
                            response = self.call_azure_api(
                                model=model,
                                messages=messages,
                                tools=tools,
                                max_tokens=max_tokens,
                                temperature=temperature,
                            )
                            return response.choices[0].message.content
                    except RateLimitError as e:
                        logger.exception(f"Rate Limit Error calling Azure: {e}")
                else:
                    logger.info(
                        f"Calling OpenAI with model {model}."
                    )
                    with Timer():
                        return self.set_openai_default_api_parameters(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            tools=tools,
                        )
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
                    with Timer():
                        response = self.create_openai_chat_completion(
                            engine=engine,
                            base_url=region_url,
                            api_key=api_key,
                            model=model,
                            messages=messages,
                            tools=tools,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                        return response.choices[0].message.content
                except (RateLimitError, APITimeoutError, InternalServerError) as e:
                    logger.exception(f"RateLimitError calling {region_url}: {e}")
            raise Exception("No Azure regions available")
        except (RateLimitError, APITimeoutError, InternalServerError) as e:
            try:
                with Timer():
                    return self.set_openai_default_api_parameters(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        tools=tools,
                    )
            except Exception as _e:
                logger.error(f"OpenAI API Key found but error: {_e}")
            logger.error(f"OpenAI API Key not found and Azure Error: {e}")
            # Raise exception to report error
            raise e
        except Exception as e:
            raise e
        return None

    def determine_openai_engine(self, model):
        engine = None
        if model in OPENAI_EXCLUSIVE_MODELS and OPENAI_API_TYPE != "azure":
            logger.info(f"Calling OpenAI exclusive model. {model}")
        elif (
            model == "gpt-4"
            or model == "gpt-4-0613"
            or model == "gpt-4-1106-preview"
            or model == "gpt-4-0125-preview"
        ):
            engine = model
        return engine

    def create_openai_chat_completion(
        self, engine, base_url, api_key, model, messages, tools, max_tokens, temperature
    ):
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=base_url,
            api_version=OPENAI_API_VERSION,
            azure_deployment=AZURE_OPENAI_DEPLOYMENT,
        )
        if len(tools) == 0:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=OPENAI_TIMEOUT,
            )
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=OPENAI_TIMEOUT,
            )
        return response

    def call_azure_api(self, model, messages, tools, max_tokens, temperature) -> ChatCompletion:
        client = AzureOpenAI(
            api_key=AZURE_API_KEY,
            azure_endpoint=OPENAI_API_BASE,
            api_version=OPENAI_API_VERSION,
            azure_deployment=AZURE_OPENAI_DEPLOYMENT,
        )
        if len(tools) == 0:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=OPENAI_TIMEOUT,
            )
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=OPENAI_TIMEOUT,
            )
        return response

    @backoff.on_exception(
        backoff.expo,
        exception=(RateLimitError, APITimeoutError, InternalServerError),
        max_tries=3,
        jitter=backoff.random_jitter,
        on_backoff=lambda details: logger.error(
            f"Rate Limit or Timeout Error: {details['tries']} tries. Waiting {details['wait']:.2f} seconds."
        ),
        base=10,
        factor=2,
        max_value=40,
    )
    def set_openai_default_api_parameters(
        self, model, messages, max_tokens, temperature, tools=[], stop_sequences=[]
    ):
        client = OpenAI(api_key=OPENAI_API_KEY)
        if len(tools) == 0:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=OPENAI_TIMEOUT,
                seed=SEED,
                stream=True,
            )
            text = ""
            for chunk in response: # pylint: disable=E1133
                new_content = chunk.choices[0].delta.content
                text += new_content if new_content else ""
                if new_content:
                    print(new_content, end="", flush=True)
            print() # clear the line
            return text
        else:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=OPENAI_TIMEOUT,
                seed=SEED,  
            )
            return response.choices[0].message.content


def get_client():
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_API_TYPE = os.environ.get("OPENAI_API_TYPE", "openai")
    OPENAI_API_BASE = os.environ.get(
        "OPENAI_API_BASE", None
    )
    AZURE_API_KEY = os.environ.get(
        "AZURE_API_KEY", None
    )
    AZURE_OPENAI_DEPLOYMENT = os.environ.get(
        "AZURE_OPENAI_DEPLOYMENT", None
    )
    OPENAI_API_VERSION = os.environ.get(
        "OPENAI_API_VERSION", None
    )
    if OPENAI_API_TYPE == "anthropic":
        client = Anthropic()
        model="claude-3-opus-20240229"
    if OPENAI_API_TYPE == "openai":
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=90) if OPENAI_API_KEY else None
        model = DEFAULT_GPT4_MODEL
    elif OPENAI_API_TYPE == "azure":
        client = AzureOpenAI(
            azure_endpoint=OPENAI_API_BASE,
            api_key=AZURE_API_KEY,
            api_version=OPENAI_API_VERSION,
        )
        model=AZURE_OPENAI_DEPLOYMENT
    else:
        raise ValueError(f"Invalid OPENAI_API_TYPE: {OPENAI_API_TYPE}")
    return model, client

def get_embeddings_client() -> OpenAI | AzureOpenAI:
    client = None
    if OPENAI_EMBEDDINGS_API_TYPE == "openai":
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=90) if OPENAI_API_KEY else None
    elif OPENAI_EMBEDDINGS_API_TYPE == "azure":
        client = AzureOpenAI(
            azure_endpoint=OPENAI_EMBEDDINGS_AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            azure_deployment=OPENAI_EMBEDDINGS_AZURE_DEPLOYMENT,
            api_version=OPENAI_EMBEDDINGS_AZURE_API_VERSION,
        )
    if not client:
        raise ValueError("No Valid API key found for OpenAI or Azure!")
    return client

def test_openai_proxy():
    openai_proxy = OpenAIProxy()
    response = openai_proxy.call_openai(
        "gpt-4-0125-preview",
        [
            {
                "role": "user",
                "content": "Say this is a test",
            }
        ],
        max_tokens=100,
    )
    print((response))

def test_get_client():
    model, client = get_client()
    client.beta.assistants.create(
        model=model,
        name="Test assistant",
        description="test",
        instructions="Say this is a test",
    )

if __name__ == "__main__":
    model, client = get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[Message(
            role="user",
            content="Say this is a test",
        ).to_openai()],
        stream=True,
    )
    print("Generating response...", flush=True)
    text = ""
    for chunk in response: # pylint: disable=E1133
        new_content = chunk.choices[0].delta.content
        text += new_content if new_content else ""
        if new_content:
            print(new_content, end="", flush=True)
    print()
