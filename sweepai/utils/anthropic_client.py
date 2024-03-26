import copy
from anthropic import Anthropic
from loguru import logger
from openai import OpenAI
from sweepai.config.server import (
    DEFAULT_GPT4_32K_MODEL,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
)

# falls back to openai if model is not available
class AnthropicClient:
    def __init__(self):
        if OPENAI_API_TYPE != "anthropic":
            self.client = OpenAI(api_key=OPENAI_API_KEY, timeout=90)
            self.model = DEFAULT_GPT4_32K_MODEL
            logger.info(f"Using OpenAI model: {self.model}")
        else:
            self.client = Anthropic()
            self.model = "claude-3-opus-20240229"
            logger.info(f"Using Anthropic model: {self.model}")

    # returns the clients response object
    def get_response_message(self, messages: list[dict[str, str]], model: str = "", **kwargs):
        model = model or self.model
        # for anthropic the messages must be alternating user and assistant and we cannot have system as a role
        if OPENAI_API_TYPE == "anthropic":
            new_messages = []
            for message in messages:
                if message["role"] == "system":
                    message["role"] = "user"
                if new_messages and new_messages[-1]["role"] == message["role"]:
                    new_messages[-1]["content"] += "\n\n" + message["content"]
                else:
                    new_messages.append(copy.deepcopy(message))
            messages = new_messages
            response = self.client.messages.create(messages=messages, model=model, **kwargs)
        else:
            response = self.client.chat.completions.create(messages=messages, model=model, **kwargs)
        return response
    
    # returns the role and content from the response
    def parse_role_content_from_response(self, response):
        if OPENAI_API_TYPE != "anthropic":
            response_message = response.choices[0].message
            response_message_dict = response_message.model_dump()
            response_contents = response_message_dict.get("content", "")
            return response_contents['role'], response_contents
        else:
            response_message_dict = response.model_dump()
            if response_message_dict.get("content", ""):
                response_contents = response_message_dict.get("content", "")[0]['text']
            else:
                response_contents = ""
            return response_message_dict['role'], response_contents