import time
import traceback
from typing import Any, Literal

import backoff
import openai
from pydantic import BaseModel

from sweepai.config.client import get_description
from sweepai.config.server import (
    OPENAI_DO_HAVE_32K_MODEL_ACCESS,
    OPENAI_USE_3_5_MODEL_ONLY,
)
from sweepai.core.entities import Message, SweepContext
from sweepai.core.prompts import (
    repo_description_prefix_prompt,
    rules_prefix_prompt,
    system_message_prompt,
)
from sweepai.logn import logger
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.openai_proxy import OpenAIProxy
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.utils import Tiktoken

openai_proxy = OpenAIProxy()

OpenAIModel = (
    Literal["gpt-3.5-turbo"]
    | Literal["gpt-4"]
    | Literal["gpt-4-0613"]
    | Literal["gpt-3.5-turbo-16k"]
    | Literal["gpt-3.5-turbo-16k-0613"]
    | Literal["gpt-4-32k"]
    | Literal["gpt-4-32k-0613"]
)

ChatModel = OpenAIModel
model_to_max_tokens = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "claude-v1": 9000,
    "claude-v1.3-100k": 100000,
    "claude-instant-v1.3-100k": 100000,
    "gpt-3.5-turbo-16k-0613": 16000,
    "gpt-4-32k-0613": 32000,
    "gpt-4-32k": 32000,
}
default_temperature = (
    0.0  # Lowered to 0 for mostly deterministic results for reproducibility
)
count_tokens = Tiktoken().count


class ChatGPT(BaseModel):
    messages: list[Message] = [
        Message(
            role="system",
            content=system_message_prompt,
        )
    ]
    prev_message_states: list[list[Message]] = []
    model: ChatModel = (
        "gpt-4-32k-0613" if OPENAI_DO_HAVE_32K_MODEL_ACCESS else "gpt-4-0613"
    )
    chat_logger: ChatLogger | None
    human_message: HumanMessagePrompt | None = None
    file_change_paths: list[str] = []
    sweep_context: SweepContext | None = None
    cloned_repo: ClonedRepo | None = None
    temperature: float = default_temperature

    @classmethod
    def from_system_message_content(
        cls,
        human_message: HumanMessagePrompt,
        is_reply: bool = False,
        chat_logger=None,
        sweep_context=None,
        cloned_repo: ClonedRepo | None = None,
        **kwargs,
    ):
        content = system_message_prompt
        repo = kwargs.get("repo")
        if repo:
            repo_info = get_description(repo)
            repo_description = repo_info["description"]
            repo_rules = repo_info["rules"]
            if repo_description:
                content += f"{repo_description_prefix_prompt}\n{repo_description}"
            if repo_rules:
                content += f"{rules_prefix_prompt}:\n{repo_rules}"
        messages = [Message(role="system", content=content, key="system")]

        added_messages = human_message.construct_prompt()  # [ { role, content }, ... ]
        for msg in added_messages:
            messages.append(Message(**msg))

        return cls(
            messages=messages,
            human_message=human_message,
            chat_logger=chat_logger,
            sweep_context=sweep_context,
            cloned_repo=cloned_repo,
            **kwargs,
        )

    @classmethod
    def from_system_message_string(
        cls, prompt_string: str, chat_logger: ChatLogger, **kwargs
    ) -> Any:
        return cls(
            messages=[Message(role="system", content=prompt_string, key="system")],
            chat_logger=chat_logger,
            **kwargs,
        )

    def select_message_from_message_key(
        self, message_key: str, message_role: str = None
    ):
        if message_role:
            return [
                message
                for message in self.messages
                if message.key == message_key and message.role == message_role
            ][0]
        return [message for message in self.messages if message.key == message_key][0]

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

    def delete_file_from_system_message(self, file_path: str):
        self.human_message.delete_file(file_path)

    def update_message_content_from_message_key(
        self, message_key: str, new_content: str, message_role: str = None
    ):
        if [message for message in self.messages if message.key == message_key]:
            self.select_message_from_message_key(
                message_key, message_role=message_role
            ).content = new_content

    def chat(
        self,
        content: str,
        model: ChatModel | None = None,
        message_key: str | None = None,
        temperature: float | None = None,
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
                ),
                key=message_key,
            )
        )
        self.prev_message_states.append(self.messages)
        return self.messages[-1].content

    # @file_cache(ignore_params=["chat_logger", "sweep_context", "cloned_repo"])
    def call_openai(
        self,
        model: ChatModel | None = None,
        temperature=temperature,
    ):
        if self.chat_logger is not None:
            tickets_allocated = 120 if self.chat_logger.is_paying_user() else 5
            tickets_count = self.chat_logger.get_ticket_count()
            purchased_tickets = self.chat_logger.get_ticket_count(purchased=True)
            if tickets_count < tickets_allocated:
                model = model or self.model
                logger.info(f"{tickets_count} tickets found in MongoDB, using {model}")
            elif purchased_tickets > 0:
                model = model or self.model
                logger.info(
                    f"{purchased_tickets} purchased tickets found in MongoDB, using {model}"
                )
            else:
                model = "gpt-3.5-turbo-16k-0613"

        count_tokens = Tiktoken().count
        messages_length = sum(
            [count_tokens(message.content or "") for message in self.messages]
        )
        max_tokens = (
            model_to_max_tokens[model] - int(messages_length) - 400
        )  # this is for the function tokens
        logger.info("file_change_paths" + str(self.file_change_paths))
        if len(self.file_change_paths) > 0:
            self.file_change_paths.remove(self.file_change_paths[0])
        if max_tokens < 0:
            if len(self.file_change_paths) > 0:
                pass
            else:
                logger.error(
                    f"Input to OpenAI:\n{self.messages_dicts}\n{traceback.format_exc()}"
                )
                raise ValueError(f"Message is too long, max tokens is {max_tokens}")
        messages_raw = "\n".join([(message.content or "") for message in self.messages])
        logger.info(f"Input to call openai:\n{messages_raw}")

        messages_dicts = [self.messages_dicts[0]]
        for message_dict in self.messages_dicts[:1]:
            if message_dict["role"] == messages_dicts[-1]["role"]:
                messages_dicts[-1]["content"] += "\n" + message_dict["content"]
            messages_dicts.append(message_dict)

        gpt_4_buffer = 800
        if int(messages_length) + gpt_4_buffer < 6000 and model == "gpt-4-32k-0613":
            model = "gpt-4-0613"
            max_tokens = (
                model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer
            )  # this is for the function tokens
        if (
            model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer < 1000
            and not OPENAI_DO_HAVE_32K_MODEL_ACCESS
        ):  # use 16k if it's OOC and no 32k
            model = "gpt-3.5-turbo-16k-0613"
            max_tokens = (
                model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer
            )
        if "gpt-4" in model:
            max_tokens = min(max_tokens, 5000)
        # Fix for self hosting where TPM limit is super low for GPT-4
        if OPENAI_USE_3_5_MODEL_ONLY:
            model = "gpt-3.5-turbo-16k-0613"
            max_tokens = (
                model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer
            )
        logger.info(f"Using the model {model}, with {max_tokens} tokens remaining")
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
                )
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

    async def achat(
        self,
        content: str,
        model: ChatModel | None = None,
        message_key: str | None = None,
    ):
        self.messages.append(Message(role="user", content=content, key=message_key))
        model = model or self.model
        response = await self.acall_openai(model=model)
        self.messages.append(
            Message(role="assistant", content=response, key=message_key)
        )
        self.prev_message_states.append(self.messages)
        return self.messages[-1].content

    async def acall_openai(
        self,
        model: ChatModel | None = None,
    ):
        if self.chat_logger is not None:
            tickets_allocated = 120 if self.chat_logger.is_paying_user() else 5
            tickets_count = self.chat_logger.get_ticket_count()
            if tickets_count < tickets_allocated:
                model = model or self.model
                logger.info(f"{tickets_count} tickets found in MongoDB, using {model}")
            else:
                model = "gpt-3.5-turbo-16k-0613"

        count_tokens = Tiktoken().count
        messages_length = sum(
            [count_tokens(message.content or "") for message in self.messages]
        )
        max_tokens = (
            model_to_max_tokens[model] - int(messages_length) - 400
        )  # this is for the function tokens
        # TODO: Add a check to see if the message is too long
        logger.info("file_change_paths" + str(self.file_change_paths))
        if len(self.file_change_paths) > 0:
            self.file_change_paths.remove(self.file_change_paths[0])
        if max_tokens < 0:
            if len(self.file_change_paths) > 0:
                pass
            else:
                logger.error(
                    f"Input to OpenAI:\n{self.messages_dicts}\n{traceback.format_exc()}"
                )
                raise ValueError(f"Message is too long, max tokens is {max_tokens}")
        messages_raw = "\n".join([(message.content or "") for message in self.messages])
        logger.info(f"Input to call openai:\n{messages_raw}")

        messages_dicts = [self.messages_dicts[0]]
        for message_dict in self.messages_dicts[:1]:
            if message_dict["role"] == messages_dicts[-1]["role"]:
                messages_dicts[-1]["content"] += "\n" + message_dict["content"]
            messages_dicts.append(message_dict)

        gpt_4_buffer = 800
        if int(messages_length) + gpt_4_buffer < 6000 and model == "gpt-4-32k-0613":
            model = "gpt-4-0613"
            max_tokens = (
                model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer
            )  # this is for the function tokens
        if "gpt-4" in model:
            max_tokens = min(max_tokens, 5000)
        # Fix for self hosting where TPM limit is super low for GPT-4
        if OPENAI_USE_3_5_MODEL_ONLY:
            model = "gpt-3.5-turbo-16k-0613"
            max_tokens = (
                model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer
            )
        logger.info(f"Using the model {model}, with {max_tokens} tokens remaining")
        global retry_counter
        retry_counter = 0

        async def fetch():
            for time_to_sleep in [10, 10, 20, 30, 60]:
                global retry_counter
                retry_counter += 1
                token_sub = retry_counter * 200
                try:
                    output = (
                        (
                            await openai.ChatCompletion.acreate(
                                model=model,
                                messages=self.messages_dicts,
                                max_tokens=max_tokens - token_sub,
                                temperature=default_temperature,
                            )
                        )
                        .choices[0]
                        .message["content"]
                    )
                    if self.chat_logger is not None:
                        self.chat_logger.add_chat(
                            {
                                "model": model,
                                "messages": self.messages_dicts,
                                "max_tokens": max_tokens - token_sub,
                                "temperature": default_temperature,
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
                        except Exception as e:
                            logger.warning(e)
                    return output
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.warning(f"{e}\n{traceback.format_exc()}")
                    time.sleep(time_to_sleep + backoff.random_jitter(5))

        result = await fetch()
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
