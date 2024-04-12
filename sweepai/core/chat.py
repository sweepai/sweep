from math import inf
import os
import re
import time
import traceback
from typing import Any, Literal

from anthropic import Anthropic, BadRequestError, AnthropicBedrock
from openai import OpenAI
import backoff
from loguru import logger
from pydantic import BaseModel

from sweepai.agents.agent_utils import ensure_additional_messages_length
from sweepai.config.client import get_description
from sweepai.config.server import (
    ANTHROPIC_AVAILABLE,
    AWS_ACCESS_KEY,
    AWS_REGION,
    AWS_SECRET_KEY,
    DEFAULT_GPT4_32K_MODEL,
    PAREA_API_KEY
)
from sweepai.core.entities import Message
from sweepai.core.prompts import repo_description_prefix_prompt, system_message_prompt
from sweepai.logn.cache import file_cache
from sweepai.utils.anthropic_client import sanitize_anthropic_messages
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.openai_proxy import OpenAIProxy
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.utils import Tiktoken
from parea import Parea

parea_client = None
try:
    if PAREA_API_KEY:
        parea_client = Parea(api_key=PAREA_API_KEY)
except Exception as e:
    logger.info(f"Failed to initialize Parea client: {e}")

openai_proxy = OpenAIProxy()

OpenAIModel = (
    Literal["gpt-3.5-turbo"]
    | Literal["gpt-3.5-turbo-1106"]
    | Literal["gpt-3.5-turbo-16k"]
    | Literal["gpt-3.5-turbo-16k-0613"]
    | Literal["gpt-4-1106-preview"]
    | Literal["gpt-4-0125-preview"]
)

AnthropicModel = (
    Literal["claude-3-haiku-20240307"]
    | Literal["claude-3-sonnet-20240229"]
    | Literal["claude-3-opus-20240229"]
)

ChatModel = OpenAIModel | AnthropicModel
model_to_max_tokens = {
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "gpt-4-1106-preview": 128000,
    "gpt-4-0125-preview": 128000,
    "gpt-4-turbo-2024-04-09": 128000,
    "claude-v1": 9000,
    "claude-v1.3-100k": 100000,
    "claude-instant-v1.3-100k": 100000,
    "anthropic.claude-3-haiku-20240229-v1:0": 200000,
    "anthropic.claude-3-sonnet-20240229-v1:0": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-haiku-20240307": 200000,
    "gpt-3.5-turbo-16k-0613": 16000,
}
default_temperature = 0.1

class MessageList(BaseModel):
    messages: list[Message] = [
        Message(
            role="system",
            content=system_message_prompt,
        )
    ]

    @property
    def messages_dicts(self):
        # Remove the key from the message object before sending to OpenAI
        cleaned_messages = [message.to_openai() for message in self.messages]
        return cleaned_messages

    def delete_messages_from_chat(
        self, key_to_delete: str, delete_user=True, delete_assistant=True
    ):
        self.messages = [
            message
            for message in self.messages
            if not (
                key_to_delete in (message.key or "")
                and (
                    delete_user
                    and message.role == "user"
                    or delete_assistant
                    and message.role == "assistant"
                )
            )  # Only delete if message matches key to delete and role should be deleted
        ]

def determine_model_from_chat_logger(chat_logger: ChatLogger, model: str):
    if chat_logger is not None:
        if (
            chat_logger.active is False
            and not chat_logger.is_paying_user()
            and not chat_logger.is_consumer_tier()
        ):
            raise ValueError(
                "You have no more tickets! Please upgrade to a paid plan."
            )
        else:
            tickets_allocated = inf if chat_logger.is_paying_user() else 5
            tickets_count = chat_logger.get_ticket_count()
            purchased_tickets = chat_logger.get_ticket_count(purchased=True)
            if tickets_count < tickets_allocated:
                logger.info(
                    f"{tickets_count} tickets found in MongoDB, using {model}"
                )
                return model
            elif purchased_tickets > 0:
                
                logger.info(
                    f"{purchased_tickets} purchased tickets found in MongoDB, using {model}"
                )
                return model
            else:
                raise ValueError(
                    f"Tickets allocated: {tickets_allocated}, tickets found: {tickets_count}. You have no more tickets!"
                )
    return model

tool_call_parameters = {
    "make_change": ["justification", "file_name", "original_code", "new_code"],
    "create_file": ["justification", "file_name", "file_path", "contents"],
    "submit_result": ["justification"],
}

# returns a dictionary of the tool call parameters, assumes correct
def parse_function_call_parameters(tool_call_contents: str, parameters: list[str]) -> dict[str, Any]:
    tool_args = {}
    for param in parameters:
        param_regex = rf'<{param}>\s*(?P<{param}>.*?)\s*<\/{param}>'
        match = re.search(param_regex, tool_call_contents, re.DOTALL)
        if match:
            param_contents = match.group(param)
            tool_args[param] = param_contents
    return tool_args

# parse llm response for tool calls in xml format
def parse_function_calls_for_openai(response_contents: str) -> list[dict[str, str]]:
    tool_calls = []
    # first get all tool calls
    for tool_name in tool_call_parameters.keys():
        tool_call_regex = rf'<{tool_name}>\s*(?P<function_call>.*?)\s*<\/{tool_name}>'
        tool_call_matches = re.finditer(tool_call_regex, response_contents, re.DOTALL)
        # now we extract its parameters
        for tool_call_match in tool_call_matches:
            tool_call_contents = tool_call_match.group("function_call")
            # get parameters based off of tool name
            parameters = tool_call_parameters[tool_name]
            tool_call = { "tool": tool_name, 
                        "arguments": parse_function_call_parameters(tool_call_contents, parameters) 
                        }
            tool_calls.append(tool_call)
    return tool_calls

class ChatGPT(MessageList):
    prev_message_states: list[list[Message]] = []
    model: ChatModel = DEFAULT_GPT4_32K_MODEL
    chat_logger: ChatLogger | None = None
    human_message: HumanMessagePrompt | None = None
    file_change_paths: list[str] = []
    cloned_repo: ClonedRepo | None = None
    temperature: float = default_temperature

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_system_message_content(
        cls,
        human_message: HumanMessagePrompt,
        is_reply: bool = False,
        chat_logger=None,
        cloned_repo: ClonedRepo | None = None,
        **kwargs,
    ):
        content = system_message_prompt
        repo = kwargs.get("repo")
        if repo:
            repo_info = get_description(repo)
            repo_description = repo_info["description"]
            repo_info["rules"]
            if repo_description:
                content += f"{repo_description_prefix_prompt}\n{repo_description}"
        messages = [Message(role="system", content=content, key="system")]

        added_messages = human_message.construct_prompt()  # [ { role, content }, ... ]
        for msg in added_messages:
            messages.append(Message(**msg))
        messages = ensure_additional_messages_length(messages)

        return cls(
            messages=messages,
            human_message=human_message,
            chat_logger=chat_logger,
            cloned_repo=cloned_repo,
            **kwargs,
        )

    @classmethod
    def from_system_message_string(
        cls, prompt_string: str, chat_logger: ChatLogger | None = None, **kwargs
    ) -> Any:
        return cls(
            messages=[Message(role="system", content=prompt_string, key="system")],
            chat_logger=chat_logger,
            **kwargs,
        )

    def delete_messages_from_chat(
        self, key_to_delete: str, delete_user=True, delete_assistant=True
    ):
        self.messages = [
            message
            for message in self.messages
            if not (
                key_to_delete in (message.key or "")
                and (
                    delete_user
                    and message.role == "user"
                    or delete_assistant
                    and message.role == "assistant"
                )
            )  # Only delete if message matches key to delete and role should be deleted
        ]

    def chat(
        self,
        content: str,
        model: ChatModel | None = None,
        message_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop_sequences: list[str] = [],
    ):
        self.messages.append(Message(role="user", content=content, key=message_key))
        model = model or self.model
        temperature = temperature or self.temperature or default_temperature
        self.messages.append(
            Message(
                role="assistant",
                content=self.call_openai(
                    model=model,
                    temperature=temperature,
                    requested_max_tokens=max_tokens,
                    stop_sequences=stop_sequences,
                ),
                key=message_key,
            )
        )
        self.prev_message_states.append(self.messages)
        return self.messages[-1].content

    @file_cache(ignore_params=["chat_logger", "cloned_repo"])
    def call_openai(
        self,
        model: ChatModel | None = None,
        temperature=temperature,
        requested_max_tokens: int | None = None,
        stop_sequences: list[str] = [],
    ):
        model = determine_model_from_chat_logger(chat_logger=self.chat_logger, model=model)
        if model not in model_to_max_tokens:
            raise ValueError(f"Model {model} not supported")
        count_tokens = Tiktoken().count
        messages_length = sum(
            [count_tokens(message.content or "") for message in self.messages]
        )
        max_tokens = (
            model_to_max_tokens[model] - int(messages_length) - 400
        )  # this is for the function tokens
        messages_raw = "\n".join([(message.content or "") for message in self.messages])
        logger.info(f"Input to call openai:\n{messages_raw}")
        if len(self.file_change_paths) > 0:
            self.file_change_paths.remove(self.file_change_paths[0])
        if max_tokens < 0:
            if len(self.file_change_paths) > 0:
                pass
            else:
                raise ValueError(f"Message is too long, max tokens is {max_tokens}")
        messages_dicts = [self.messages_dicts[0]]
        for message_dict in self.messages_dicts[:1]:
            if message_dict["role"] == messages_dicts[-1]["role"]:
                messages_dicts[-1]["content"] += "\n" + message_dict["content"]
            messages_dicts.append(message_dict)
        max_tokens = min(max_tokens, 4096)
        max_tokens = (
            min(requested_max_tokens, max_tokens)
            if requested_max_tokens
            else max_tokens
        )
        logger.info(f"Using the model {model} with {messages_length} input tokens and {max_tokens} tokens remaining")
        global retry_counter
        retry_counter = 0

        @backoff.on_exception(
            backoff.expo,
            Exception,
            max_tries=16,
            jitter=backoff.random_jitter,
        )
        def fetch():
            global retry_counter
            retry_counter += 1
            token_sub = retry_counter * 200
            try:
                output = None
                output = openai_proxy.call_openai(
                    model=model,
                    messages=self.messages_dicts,
                    max_tokens=max_tokens - token_sub,
                    temperature=temperature,
                    stop_sequences=stop_sequences,
                ).choices[0].message.content
                if self.chat_logger is not None:
                    self.chat_logger.add_chat(
                        {
                            "model": model,
                            "messages": self.messages_dicts,
                            "max_tokens": max_tokens - token_sub,
                            "temperature": temperature,
                            "output": output,
                        }
                    )
                if self.chat_logger:
                    try:
                        token_count = count_tokens(output)
                        posthog.capture(
                            self.chat_logger.data.get("username"),
                            "call_openai",
                            {
                                "model": model,
                                "max_tokens": max_tokens - token_sub,
                                "input_tokens": messages_length,
                                "output_tokens": token_count,
                                "repo_full_name": self.chat_logger.data.get(
                                    "repo_full_name"
                                ),
                                "username": self.chat_logger.data.get("username"),
                                "pr_number": self.chat_logger.data.get("pr_number"),
                                "issue_url": self.chat_logger.data.get("issue_url"),
                            },
                        )
                    except SystemExit:
                        raise SystemExit
                    except Exception as e2:
                        logger.warning(e2)
                return output
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.warning(f"{e}\n{traceback.format_exc()}")
                raise e

        result = fetch()
        logger.info(f"Output to call openai:\n{result}")
        return result
    
    def chat_anthropic(
        self,
        content: str,
        assistant_message_content: str = "",
        model: ChatModel = "claude-3-haiku-20240307",
        message_key: str | None = None,
        temperature: float | None = None,
        stop_sequences: list[str] = [],
        max_tokens: int = 4096,
        use_openai: bool = False,
    ):
        # use openai
        if use_openai:
            OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
            assert OPENAI_API_KEY
            self.model = 'gpt-4-turbo'
        else:
            ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
            assert ANTHROPIC_API_KEY
            self.model = model
        self.messages.append(Message(role="user", content=content, key=message_key))
        if assistant_message_content:
            self.messages.append(Message(role="assistant", content=assistant_message_content))
        temperature = temperature or self.temperature or default_temperature
        messages_string = '\n\n'.join([message.content for message in self.messages])
        logger.debug(f"Calling anthropic with model {model}\nMessages:{messages_string}\nInput:\n{content}")
        system_message = "\n\n".join([message.content for message in self.messages if message.role == "system"])
        content = ""
        e = None
        NUM_ANTHROPIC_RETRIES = 4
        for i in range(NUM_ANTHROPIC_RETRIES):
            try:
                @file_cache(redis=True) # must be in the inner scope because this entire function manages state
                def call_anthropic(
                    message_dicts: list[dict[str, str]], 
                    system_message: str = system_message, 
                    model: str = model,
                    use_openai: bool = use_openai,
                ) -> str: # add system message and model to cache
                    if use_openai:
                        client = OpenAI()
                    else:
                        if ANTHROPIC_AVAILABLE and "opus" not in model:
                            if "anthropic" not in model:
                                model = f"anthropic.{model}-v1:0"
                                self.model = f"anthropic.{self.model}-v1:0"
                            client = AnthropicBedrock(
                                aws_access_key=AWS_ACCESS_KEY,
                                aws_secret_key=AWS_SECRET_KEY,
                                aws_region=AWS_REGION,
                            )
                        else:
                            client = Anthropic(api_key=ANTHROPIC_API_KEY)
                    if parea_client:
                        if use_openai:
                            parea_client.wrap_openai_client(client)
                        else:
                            parea_client.wrap_anthropic_client(client)
                    if use_openai:
                        response = client.chat.completions.create(
                            model=model,
                            messages=self.messages_dicts,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            stop=stop_sequences,
                        ).choices[0].message.content
                    else:
                        response = client.messages.create(
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            messages=message_dicts,
                            system=system_message,
                            stop_sequences=stop_sequences,
                        ).content[0].text
                    return response
                if use_openai:
                    message_dicts = [
                        {
                            "role": message.role,
                            "content": message.content,
                        } for message in self.messages
                    ]
                    message_dicts = sanitize_anthropic_messages(message_dicts)
                else: 
                    message_dicts = [
                        {
                            "role": message.role,
                            "content": message.content,
                        } for message in self.messages if message.role != "system"
                    ]
                    message_dicts = sanitize_anthropic_messages(message_dicts)
                content = call_anthropic(message_dicts, self.messages[0].content, self.model, use_openai=use_openai)
                break
            except BadRequestError as e_:
                e = e_ # sometimes prompt is too long
                raise e_
            except Exception as e_:
                logger.exception(e_)
                e = e_
                time.sleep(4 * 2 ** i) # faster debugging
        else:
            raise Exception("Anthropic call failed") from e
        self.messages.append(
            Message(
                role="assistant",
                content=content,
                key=message_key,
            )
        )
        logger.debug(f'{"Openai" if use_openai else "Anthropic"} response: {self.messages[-1].content}')
        self.prev_message_states.append(self.messages)
        return self.messages[-1].content

    @property
    def messages_dicts(self):
        # Remove the key from the message object before sending to OpenAI
        cleaned_messages = [message.to_openai() for message in self.messages]
        return cleaned_messages

    def undo(self):
        if len(self.prev_message_states) > 0:
            self.messages = self.prev_message_states.pop()
        return self.messages
