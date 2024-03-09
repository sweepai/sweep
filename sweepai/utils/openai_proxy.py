import random

from loguru import logger
from openai import AzureOpenAI, OpenAI

from sweepai.config.server import (
    AZURE_API_KEY,
    AZURE_OPENAI_DEPLOYMENT,
    BASERUN_API_KEY,
    MULTI_REGION_CONFIG,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
    OPENAI_API_VERSION,
)
from sweepai.core.entities import Message
from sweepai.logn.cache import file_cache

if BASERUN_API_KEY is not None:
    pass

OPENAI_TIMEOUT = 300  # one minute

OPENAI_EXCLUSIVE_MODELS = [
    "gpt-4-0125-preview",
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
    def call_openai_with_retry(
        self,
        model: str,
        messages: list[Message],
        tools: list[str] = [],
        max_tokens: int = 256,
        temperature: float = 0.0,
        seed: int = 0,
    ):
        e = None
        for current_max_tokens in [
            max_tokens,
            2 * max_tokens,
            4 * max_tokens,
            8 * max_tokens,
            16 * max_tokens,
        ]:
            logger.info(f"Calling OpenAI with {current_max_tokens} tokens...")
            try:
                response = self.call_openai(
                    model, messages, tools, current_max_tokens, temperature, seed
                )
                if response.choices[0].finish_reason != "length":
                    return response
                logger.warning(
                    f"OpenAI call finish_reason returned {response.choices[0].finish_reason}, retrying with {current_max_tokens * 2}..."
                )
            except Exception as e:
                logger.exception(
                    f"Error calling OpenAI: {e}, retrying with {current_max_tokens * 2}..."
                )
        if e is not None:
            raise Exception("OpenAI call failed") from e
        raise Exception("OpenAI call failed")

    @file_cache(ignore_params=[])
    def call_openai(
        self,
        model: str,
        messages: list[Message],
        tools: list[str] = [],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        seed: int = 0,
    ):
        try:
            engine = self.determine_openai_engine(model)
            if OPENAI_API_TYPE is None or engine is None:
                response = self.set_openai_default_api_parameters(
                    model, messages, max_tokens, temperature
                )
                return response
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
                if OPENAI_API_TYPE == "azure":
                    response = self.call_azure_api(
                        model, messages, tools, max_tokens, temperature
                    )
                    return response
                return self.set_openai_default_api_parameters(
                    model, messages, tools, max_tokens, temperature
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
                    response = self.create_openai_chat_completion(
                        engine,
                        region_url,
                        api_key,
                        model,
                        messages,
                        tools,
                        max_tokens,
                        temperature,
                    )
                    return response
                except Exception as e:
                    logger.exception(f"Error calling {region_url}: {e}")
            raise Exception("No Azure regions available")
        except SystemExit:
            raise SystemExit
        except Exception as e:
            try:
                if OPENAI_API_TYPE == "azure":
                    response = self.call_azure_api(
                        model, messages, tools, max_tokens, temperature
                    )
                    return response
                return self.set_openai_default_api_parameters(
                    model, messages, tools, max_tokens, temperature
                )

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
            model == "gpt-4"
            or model == "gpt-4-0613"
            or model == "gpt-4-1106-preview"
            or model == "gpt-4-0125-preview"
        ):
            engine = model
        elif model == "gpt-4-32k" or model == "gpt-4-32k-0613":
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

    def call_azure_api(self, model, messages, tools, max_tokens, temperature):
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

    def set_openai_default_api_parameters(
        self, model, messages, max_tokens, temperature, tools = []
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
            )
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
        return response


if __name__ == "__main__":
    openai_proxy = OpenAIProxy()
    response = openai_proxy.call_openai_with_retry(
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
