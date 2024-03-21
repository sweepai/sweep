from math import inf
import traceback
from typing import Any, Literal

import backoff
from loguru import logger
from pydantic import BaseModel

from sweepai.agents.agent_utils import ensure_additional_messages_length
from sweepai.config.client import get_description
from sweepai.config.server import (
    DEFAULT_GPT4_32K_MODEL,
)
from sweepai.core.entities import Message
from sweepai.core.prompts import repo_description_prefix_prompt, system_message_prompt
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.openai_proxy import OpenAIProxy
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.utils import Tiktoken

openai_proxy = OpenAIProxy()

OpenAIModel = (
    Literal["gpt-3.5-turbo"]
    | Literal["gpt-3.5-turbo-1106"]
    | Literal["gpt-3.5-turbo-16k"]
    | Literal["gpt-3.5-turbo-16k-0613"]
    | Literal["gpt-4-1106-preview"]
    | Literal["gpt-4-0125-preview"]
)

ChatModel = OpenAIModel
model_to_max_tokens = {
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "gpt-4-1106-preview": 128000,
    "gpt-4-0125-preview": 128000,
    "claude-v1": 9000,
    "claude-v1.3-100k": 100000,
    "claude-instant-v1.3-100k": 100000,
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
                ),
                key=message_key,
            )
        )
        self.prev_message_states.append(self.messages)
        return self.messages[-1].content

    # @file_cache(ignore_params=["chat_logger", "cloned_repo"])
    def call_openai(
        self,
        model: ChatModel | None = None,
        temperature=temperature,
        requested_max_tokens: int | None = None,
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

    @property
    def messages_dicts(self):
        # Remove the key from the message object before sending to OpenAI
        cleaned_messages = [message.to_openai() for message in self.messages]
        return cleaned_messages

    def undo(self):
        if len(self.prev_message_states) > 0:
            self.messages = self.prev_message_states.pop()
        return self.messages
