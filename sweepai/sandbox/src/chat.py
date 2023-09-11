import os
import time
from typing import Literal

import openai
import backoff
import openai
from loguru import logger
from pydantic import BaseModel
import tiktoken

from src.diff import format_contents, generate_new_file_from_patch, is_markdown
from src.prompts import (
    sandbox_code_repair_modify_system_prompt,
    sandbox_code_repair_modify_prompt,
)

try:
    from typing import Self
except ImportError:
    from typing import TypeVar

    Self = TypeVar("Self")

openai.api_key = os.getenv("OPENAI_API_KEY")


class Message(BaseModel):
    role: Literal["system"] | Literal["user"] | Literal["assistant"] | Literal[
        "function"
    ]
    content: str | None = None
    name: str | None = None
    function_call: dict | None = None
    key: str | None = None

    @classmethod
    def from_tuple(cls, tup: tuple[str | None, str | None]) -> Self:
        if tup[0] is None:
            return cls(role="assistant", content=tup[1])
        else:
            return cls(role="user", content=tup[0])

    def to_openai(self) -> str:
        obj = {
            "role": self.role,
            "content": self.content,
        }
        if self.function_call:
            obj["function_call"] = self.function_call
        if self.role == "function":
            obj["name"] = self.name
        return obj


OpenAIModel = (
    Literal["gpt-3.5-turbo"]
    | Literal["gpt-4"]
    | Literal["gpt-4-0613"]
    | Literal["gpt-3.5-turbo-16k"]
    | Literal["gpt-3.5-turbo-16k-0613"]
    | Literal["gpt-4-32k"]
    | Literal["gpt-4-32k-0613"]
)

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
temperature = 0.0  # Lowered to 0 for mostly deterministic results for reproducibility

tiktoken_model = None


def count_tokens(text: str):
    if tiktoken_model is None:
        tiktoken_model = tiktoken.encoding_for_model("gpt-4")
    return len(tiktoken_model.encode(text, disallowed_special=()))


class ChatGPT(BaseModel):
    messages: list[Message] = [
        Message(
            role="system",
            content=sandbox_code_repair_modify_system_prompt,
        )
    ]
    model: OpenAIModel = "gpt-4-32k-0613"
    file_change_paths: list = []

    def chat(
        self,
        content: str,
        model: OpenAIModel | None = None,
        message_key: str | None = None,
    ):
        self.messages.append(Message(role="user", content=content, key=message_key))
        model = model or self.model
        response = self.call_openai(model=model)
        self.messages.append(
            Message(role="assistant", content=response, key=message_key)
        )
        return self.messages[-1].content

    def call_openai(self, model: OpenAIModel | None = None):
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
                logger.error(f"Input to OpenAI:\n{self.messages_dicts}")
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
        logger.info(f"Using the model {model}, with {max_tokens} tokens remaining")
        global retry_counter
        retry_counter = 0

        @backoff.on_exception(
            backoff.expo,
            Exception,
            max_tries=5,
            jitter=backoff.random_jitter,
        )
        def fetch():
            global retry_counter
            retry_counter += 1
            token_sub = retry_counter * 200
            try:
                output = (
                    openai.ChatCompletion.create(
                        model=model,
                        messages=self.messages_dicts,
                        max_tokens=max_tokens - token_sub,
                        temperature=temperature,
                    )
                    .choices[0]
                    .message["content"]
                )
                return output
            except Exception as e:
                logger.warning(e)
                raise e

        result = fetch()
        logger.info(f"Output to call openai:\n{result}")
        return result

    async def achat(
        self,
        content: str,
        model: OpenAIModel | None = None,
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
        model: OpenAIModel | None = None,
    ):
        if self.chat_logger is not None:
            tickets_allocated = 120 if self.chat_logger.is_paying_user() else 5
            tickets_count = self.chat_logger.get_ticket_count()
            if tickets_count < tickets_allocated:
                model = model or self.model
                logger.warning(
                    f"{tickets_count} tickets found in MongoDB, using {model}"
                )
            else:
                model = "gpt-3.5-turbo-16k-0613"

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
                logger.error(f"Input to OpenAI:\n{self.messages_dicts}")
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
                                temperature=temperature,
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
                                "temperature": temperature,
                                "output": output,
                            }
                        )
                    return output
                except Exception as e:
                    logger.warning(e)
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


def clean_logs(logs: str) -> str:
    return "\n".join(
        line for line in logs.split("\n") if not line.startswith("[warn]")
    ).strip()


def fix_file(filename: str, code: str, stdout: str):
    chat = ChatGPT()
    response = chat.chat(
        sandbox_code_repair_modify_prompt.format(
            filename=filename, code=code, stdout=stdout
        )
    )
    updated_file, _errors = generate_new_file_from_patch(response, code)

    file_markdown = is_markdown(filename)
    updated_file = format_contents(updated_file, file_markdown)
    logger.info("Updated file based on logs")
    return updated_file


test_stdout = """
$ /repo/node_modules/.bin/eslint test1/test2.js

/repo/test1/test2.js
  1:1  error  Unexpected use of 'print'  no-restricted-globals

✖ 1 problem (1 error, 0 warnings)

error Command failed with exit code 1.
"""

if __name__ == "__main__":
    print(fix_file("test1/test2.js", "print('hello world')", test_stdout))
