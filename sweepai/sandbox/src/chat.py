import os
import re
from typing import Literal

import backoff
import openai
import tiktoken
from loguru import logger
from pydantic import BaseModel, Field
from sweepai.sandbox.src.chat_logger import ChatLogger
from sweepai.sandbox.src.diff import format_contents, generate_new_file_from_patch, is_markdown
from sweepai.sandbox.src.prompts import (
    sandbox_code_repair_modify_prompt,
    sandbox_code_repair_modify_system_prompt,
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
    global tiktoken_model
    tiktoken_model = tiktoken_model or tiktoken.encoding_for_model("gpt-4")
    return len(tiktoken_model.encode(text, disallowed_special=()))




class OpenAIProxy:
    def __init__(self):
        pass

    def call_openai(self, model, messages, max_tokens, temperature):
        try:
            engine = None
            if (
                model == "gpt-3.5-turbo-16k"
                or model == "gpt-3.5-turbo-16k-0613"
                and os.getenv("OPENAI_API_ENGINE_GPT35") is not None
            ):
                engine = os.getenv("OPENAI_API_ENGINE_GPT35")
            elif (
                model == "gpt-4"
                or model == "gpt-4-0613"
                and os.getenv("OPENAI_API_ENGINE_GPT4") is not None
            ):
                engine = os.getenv("OPENAI_API_ENGINE_GPT4")
            elif (
                model == "gpt-4-32k"
                or model == "gpt-4-32k-0613"
                and os.getenv("OPENAI_API_ENGINE_GPT4_32K") is not None
            ):
                engine = os.getenv("OPENAI_API_ENGINE_GPT4_32K")
            if os.getenv("OPENAI_API_TYPE") is None or engine is None:
                openai.api_key = os.getenv("OPENAI_API_KEY")
                openai.api_base = "https://api.openai.com/v1"
                openai.api_version = None
                openai.api_type = "open_ai"
                logger.info(f"Calling {model} on OpenAI.")
                response = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response["choices"][0].message.content
            OPENAI_API_BASE = os.getenv("OPENAI_API_BASE")
            logger.info(
                f"Calling {model} with engine {engine} on Azure url {OPENAI_API_BASE}."
            )
            openai.api_type = os.getenv("OPENAI_API_TYPE")
            openai.api_base = os.getenv("OPENAI_API_BASE")
            openai.api_version = os.getenv("OPENAI_API_VERSION")
            openai.api_key = os.getenv("AZURE_API_KEY")
            response = openai.ChatCompletion.create(
                engine=engine,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response["choices"][0].message.content
        except SystemExit:
            raise SystemExit
        except Exception as e:
            if os.getenv("OPENAI_API_KEY"):
                try:
                    openai.api_key = os.getenv("OPENAI_API_KEY")
                    openai.api_base = "https://api.openai.com/v1"
                    openai.api_version = None
                    openai.api_type = "open_ai"
                    logger.info(f"Calling {model} with OpenAI.")
                    response = openai.ChatCompletion.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return response["choices"][0].message.content
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.error(f"OpenAI API Key found but error: {e}")
                    raise e
            logger.error(f"OpenAI API Key not found and Azure Error: {e}")
            raise e


openai_proxy = OpenAIProxy()


class ChatGPT(BaseModel):
    messages: list[Message] = [
        Message(
            role="system",
            content=sandbox_code_repair_modify_system_prompt,
        )
    ]
    model: OpenAIModel = (
        "gpt-4-32k-0613"
        if os.getenv("OPENAI_DO_HAVE_32K_MODEL_ACCESS")
        else "gpt-4-0613"
    )
    file_change_paths: list = []
    chat_logger: ChatLogger = Field(default_factory=lambda: ChatLogger(data={}))

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
        # Check if the message is too long
        if messages_length > model_to_max_tokens[model]:
            raise ValueError(f"Message is too long, max tokens is {model_to_max_tokens[model]}, but got {messages_length}")
        logger.info("file_change_paths" + str(self.file_change_paths))
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

        gpt_4_buffer = 800
        if int(messages_length) + gpt_4_buffer < 6000 and model == "gpt-4-32k-0613":
            model = "gpt-4-0613"
            max_tokens = (
                model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer
            )  # this is for the function tokens
        if "gpt-4" in model:
            max_tokens = min(max_tokens, 5000)
        # Fix for self hosting where TPM limit is super low for GPT-4
        if os.getenv("OPENAI_USE_3_5_MODEL_ONLY"):
            model = "gpt-3.5-turbo-16k-0613"
            max_tokens = (
                model_to_max_tokens[model] - int(messages_length) - gpt_4_buffer
            )

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
                output = openai_proxy.call_openai(
                    model=model,
                    messages=self.messages_dicts,
                    max_tokens=max_tokens - token_sub,
                    temperature=temperature,
                )
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


def clean_logs(logs: str):
    cleaned_logs = re.sub(r"\x1b\[.*?[@-~]", "", logs.replace("```", "\`\`\`"))
    cleaned_logs = re.sub("\n{2,}", "\n", cleaned_logs)
    cleaned_logs = cleaned_logs or "(nothing was outputted)"
    return cleaned_logs


def fix_file(filename: str, code: str, stdout: str, username: str = "anonymous"):
    chat = ChatGPT(
        chat_logger=ChatLogger(data={"username": username, "title": filename})
    )
    response = chat.chat(
        sandbox_code_repair_modify_prompt.format(
            filename=filename, code=code, stdout=clean_logs(stdout)
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
