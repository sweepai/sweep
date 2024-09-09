import copy
import os
from anthropic import Anthropic
from loguru import logger
from openai import OpenAI
from sweepai.config.server import (
    DEFAULT_GPT4_MODEL,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
    PAREA_API_KEY,
)
from parea import Parea

from sweepai.logn.cache import file_cache

parea_client = None
try:
    if PAREA_API_KEY:
        parea_client = Parea(api_key=PAREA_API_KEY)
except Exception as e:
    logger.info(f"Failed to initialize Parea client: {e}")

# we cannot have two user messages in a row
def sanitize_anthropic_messages(messages: list[dict[str, str]]):
    new_messages = []
    for message in messages:
        if message["role"] == "system":
            message["role"] = "user"
        if new_messages and new_messages[-1]["role"] == message["role"]:
            new_messages[-1]["content"] += "\n\n" + message["content"].rstrip()
        else:
            message["content"] = message["content"].rstrip()
            new_messages.append(copy.deepcopy(message))
    for message in new_messages:
        message["content"] = message["content"].rstrip()
    return new_messages

# falls back to openai if model is not available
class AnthropicClient:
    def __init__(self):
        OPENAI_API_TYPE = os.environ.get("OPENAI_API_TYPE", "anthropic")
        if OPENAI_API_TYPE != "anthropic":
            self.client = OpenAI(api_key=OPENAI_API_KEY, timeout=90)
            self.model = DEFAULT_GPT4_MODEL
            logger.info(f"Using OpenAI model: {self.model}")
        else:
            self.client = Anthropic()
            if parea_client:
                parea_client.wrap_anthropic_client(self.client)
            self.model = "claude-3-opus-20240229"
            logger.info(f"Using Anthropic model: {self.model}")

    # returns the clients response object
    @file_cache(ignore_params=["self"])
    def get_response_message(self, messages: list[dict[str, str]], model: str = "", stop_sequences: list[str] = [], **kwargs):
        model = model or self.model
        # for anthropic the messages must be alternating user and assistant and we cannot have system as a role
        if OPENAI_API_TYPE == "anthropic":
            messages = sanitize_anthropic_messages(messages)
            response = self.client.messages.create(messages=messages, model=model, stop_sequences=stop_sequences, **kwargs)
        else:
            response = self.client.chat.completions.create(messages=messages, model=model, stop=stop_sequences, **kwargs)
        return response
    
    # returns the role and content from the response
    def parse_role_content_from_response(self, response):
        if OPENAI_API_TYPE != "anthropic":
            response_message = response.choices[0].message
            response_message_dict = response_message.model_dump()
            response_contents = response_message_dict.get("content", "")
            return response_message_dict['role'], response_contents
        else:
            response_message_dict = response.model_dump()
            if response_message_dict.get("content", ""):
                response_contents = response_message_dict.get("content", "")[0]['text']
            else:
                response_contents = ""
            return response_message_dict['role'], response_contents