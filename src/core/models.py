from copy import deepcopy
import json
import os
import re
from typing import ClassVar, Literal, Self, Type

import modal
import openai
import anthropic
from loguru import logger
from pydantic import BaseModel
import backoff

from src.core.prompts import (
    system_message_prompt,
    system_message_issue_comment_prompt,
)
from src.utils.prompt_constructor import HumanMessagePrompt

# TODO: combine anthropic and openai

AnthropicModel = (
    Literal["claude-v1"]
    | Literal["claude-v1.3-100k"]
    | Literal["claude-instant-v1.1-100k"]
)
OpenAIModel = Literal["gpt-3.5-turbo"] | Literal["gpt-4"] | Literal["gpt-4-32k"]
ChatModel = OpenAIModel | AnthropicModel
model_to_max_tokens = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8096,
    "gpt-4-32k": 32000,
    "gpt-4-32k-0613": 32000,
    "claude-v1": 9000,
    "claude-v1.3-100k": 100000,
    "claude-instant-v1.3-100k": 100000,
}
count_tokens = modal.Function.lookup("utils", "Tiktoken.count")


class Message(BaseModel):
    role: Literal["system"] | Literal["user"] | Literal["assistant"]
    content: str
    key: str | None = None
    is_function_call: bool = False

class Function(BaseModel):
    class Parameters(BaseModel):
        type: str = "object"
        properties: dict
    name: str
    description: str
    parameters: Parameters


def format_for_anthropic(messages: list[Message]) -> str:
    if len(messages) > 1:
        new_messages: list[Message] = [Message(role="system", content=messages[0].content + "\n" + messages[1].content)]
        messages = messages[2:] if len(messages) >= 3 else []
    else:
        new_messages: list[Message] = []
    for message in messages:
        new_messages.append(message)
    return "\n".join(
        f"{anthropic.HUMAN_PROMPT if message.role != 'assistant' else anthropic.AI_PROMPT} {message.content}"
        for message in new_messages
    ) + (anthropic.AI_PROMPT if new_messages[-1].role != "assistant" else "")


class ChatGPT(BaseModel):
    messages: list[Message] = [
        Message(
            role="system",
            content=system_message_prompt,
        )
    ]
    prev_message_states: list[list[Message]] = []
    model: ChatModel = "gpt-4-32k-0613"
    human_message: HumanMessagePrompt | None = None
    file_change_paths = []

    @classmethod
    def from_system_message_content(
        cls, human_message: HumanMessagePrompt, is_reply: bool = False, **kwargs
    ) -> Self:
        if is_reply:
            system_message_content = system_message_issue_comment_prompt
        system_message_content = (
            system_message_prompt + "\n\n" + human_message.construct_prompt()
        )
        return cls(
            messages=[
                Message(role="system", content=system_message_content, key="system")
            ],
            human_message=human_message,
            **kwargs,
        )

    @classmethod
    def from_system_message_string(cls, prompt_string, **kwargs) -> Self:
        return cls(
            messages=[Message(role="system", content=prompt_string, key="system")],
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

    def delete_messages_from_chat(self, message_key: str):
        self.messages = [
            message for message in self.messages if message.key != message_key
        ]

    def delete_file_from_system_message(self, file_path: str):
        self.human_message.delete_file(file_path)

    def get_message_content_from_message_key(
        self, message_key: str, message_role: str = None
    ):
        return self.select_message_from_message_key(
            message_key, message_role=message_role
        ).content

    def update_message_content_from_message_key(
        self, message_key: str, new_content: str, message_role: str = None
    ):
        self.select_message_from_message_key(
            message_key, message_role=message_role
        ).content = new_content


    def chat(
        self,
        content: str,
        model: ChatModel | None = None,
        message_key: str | None = None,
        functions: list[Function] = []
    ):
        self.messages.append(Message(role="user", content=content, key=message_key))
        model = model or self.model
        if model in ["gpt-3.5-turbo", "gpt-4", "gpt-4-32k", "gpt-4-32k-0613"]:
            # might be a bug here in all of this
            response = self.call_openai(model=model, functions=functions)
            if functions:
                response, is_function_call = response
                if is_function_call:
                    self.messages.append(
                        Message(role="assistant", content=json.dumps(response), key=message_key, is_function_call=is_function_call)
                    )
                else:
                    self.messages.append(
                        Message(role="assistant", content=response, key=message_key)
                    )
            else:
                response = self.call_openai(model=model, functions=functions)
                self.messages.append(
                    Message(role="assistant", content=response, key=message_key)
                )
        else:
            response = self.call_anthropic(model=model)
            self.messages.append(
                Message(role="assistant", content=response, key=message_key)
            )
        self.prev_message_states.append(self.messages)
        return self.messages[-1].content

    def call_openai(
        self, 
        model: ChatModel | None = None,
        functions: list[Function] = []
    ):
        if model is None:
            model = self.model
        messages_length = sum(
            [count_tokens.call(message.content) for message in self.messages]
        )
        max_tokens = model_to_max_tokens[model] - int(messages_length)
        # TODO: Add a check to see if the message is too long
        logger.info("file_change_paths" + str(self.file_change_paths))
        if len(self.file_change_paths) > 0:
            self.file_change_paths.remove(self.file_change_paths[0])
        if max_tokens < 0:
            if len(self.file_change_paths) > 0:
                pass
            else:
                raise ValueError(f"Message is too long, max tokens is {max_tokens}")
        messages_raw = "\n".join([message.content for message in self.messages])
        logger.info(f"Input to call openai:\n{messages_raw}")

        if functions:
            @backoff.on_exception(
                backoff.fibo,
                Exception,
                max_tries=5,
                jitter=backoff.random_jitter,
            )
            def fetch():
                return (
                    openai.ChatCompletion.create(
                        model=model,
                        messages=self.messages_dicts,
                        max_tokens=max_tokens,
                        temperature=0.1,
                        functions=[json.loads(function.json()) for function in functions]
                    )
                    .choices[0].message
                )

            result = fetch()
            if "function_call" in result:
                result = result["function_call"], True
            else:
                result = result["content"], False
            logger.info(f"Output to call openai:\n{result}")
            return result

        else:
            @backoff.on_exception(
                backoff.fibo,
                Exception,
                max_tries=5,
                jitter=backoff.random_jitter,
            )
            def fetch():
                return (
                    openai.ChatCompletion.create(
                        model=model,
                        messages=self.messages_dicts,
                        max_tokens=max_tokens,
                        temperature=0.1,
                    )
                    .choices[0]
                    .message["content"]
                )

            result = fetch()
            logger.info(f"Output to call openai:\n{result}")
            return result

    def call_anthropic(self, model: ChatModel | None = None) -> str:
        if model is None:
            model = self.model
        messages_length = sum(
            [int(count_tokens.call(message.content) * 1.1) for message in self.messages]
        )
        max_tokens = model_to_max_tokens[model] - int(messages_length) - 1000
        logger.info(f"Number of tokens: {max_tokens}")
        messages_raw = format_for_anthropic(self.messages)
        logger.info(f"Input to call anthropic:\n{messages_raw}")

        assert os.environ.get("ANTHROPIC_API_KEY"), "Please set ANTHROPIC_API_KEY"
        client = anthropic.Client(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        @backoff.on_exception(
            backoff.fibo,
            Exception,
            max_tries=5,
            jitter=backoff.random_jitter,
        )
        def fetch() -> tuple[str, str]:
            logger.warning(f"Calling anthropic...")
            results = client.completion(
                prompt=messages_raw,
                stop_sequences=[anthropic.HUMAN_PROMPT],
                model=model,
                max_tokens_to_sample=max_tokens,
                disable_checks=True,
                temperature=0.1,
            )
            return results["completion"], results["stop_reason"]

        result, stop_reason = fetch()
        logger.warning(f"Stop reasons: {stop_reason}")
        if stop_reason == "max_tokens":
            logger.warning("Hit max tokens, running for more tokens.")
            _self = deepcopy(self)
            _self.messages.append(Message(role="assistant", content=result, key=""))
            extension = _self.call_anthropic(model=model)
            print(len(result), len(extension), len(result + extension))
            return result + extension
        logger.info(f"Output to call anthropic:\n{result}")
        return result

    @property
    def messages_dicts(self):
        # Remove the key from the message object before sending to OpenAI
        cleaned_messages = [
            {k: v for k, v in message.dict().items() if k != "key" and k != "is_function_call"}
            for message in self.messages
        ]
        return cleaned_messages

    def undo(self):
        if len(self.prev_message_states) > 0:
            self.messages = self.prev_message_states.pop()
        return self.messages


class RegexMatchError(ValueError):
    pass


class RegexMatchableBaseModel(BaseModel):
    _regex: ClassVar[str]

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        # match = re.search(file_regex, string, re.DOTALL)
        match = re.search(cls._regex, string, re.DOTALL)
        if match is None:
            logger.warning(f"Did not match {string} with pattern {cls._regex}")
            raise RegexMatchError("Did not match")
        return cls(
            **{k: (v if v else "").strip() for k, v in match.groupdict().items()},
            **kwargs,
        )


class FilesToChange(RegexMatchableBaseModel):
    files_to_modify: str
    files_to_create: str
    _regex = r"""<create>(?P<files_to_create>.*)</create>\s*<modify>(?P<files_to_modify>.*)</modify>"""


class FileChangeRequest(RegexMatchableBaseModel):
    filename: str
    instructions: str
    change_type: Literal["modify"] | Literal["create"]
    _regex = r"""^ *(?P<filename>\S*):(?P<instructions>.*)"""


class FileChange(RegexMatchableBaseModel):
    commit_message: str
    code: str
    _regex = r"""Commit Message:(?P<commit_message>.*)<new_file>(python|javascript|typescript|csharp|tsx|jsx)?(?P<code>.*)$"""

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        result = super().from_string(string, **kwargs)
        result.code = result.code.strip()
        if result.code.endswith("</new_file>"):
            result.code = result.code[: -len("</new_file>")]
        if result.code.startswith("```"):
            first_newline = result.code.find("\n")
            last_newline = result.code.rfind("\n")
            result.code = result.code[first_newline + 1 :]
            result.code = result.code[: last_newline]
        result.code += "\n"
        return result


class PullRequest(RegexMatchableBaseModel):
    title: str
    branch_name: str
    content: str
    _regex = r"""Title:(?P<title>.*)Branch Name:(?P<branch_name>.*)<content>(python|javascript|typescript|csharp|tsx|jsx)?(?P<content>.*)</content>"""


class Snippet(BaseModel):
    '''
    Start and end refer to line numbers
    '''
    
    content: str
    start: int
    end: int
    file_path: str
    is_snippet_file_start: bool = False
    is_snippet_file_end: bool = False

    def get_snippet(self):
        return "\n".join(self.content.splitlines()[self.start:self.end])

    def __add__(self, other):
        assert self.content == other.content
        assert self.file_path == other.file_path
        return Snippet(
            content=self.content,
            start=self.start,
            end=other.end,
            file_path=self.file_path
        )
    
    def __xor__(self, other: "Snippet") -> bool:
        '''
        Returns True if there is an overlap between two snippets.
        '''
        if self.file_path != other.file_path:
            return False
        return self.file_path == other.file_path and (
                (self.start <= other.start and self.end >= other.start)
                or (other.start <= self.start and other.end >= self.start)
            )
        
    def __or__(self, other: "Snippet") -> "Snippet":
        assert self.file_path == other.file_path
        return Snippet(
            content=self.content,
            start=min(self.start, other.start),
            end=max(self.end, other.end),
            file_path=self.file_path
        )
    
    @property
    def xml(self):
snippet_content = self.get_snippet()
        if not self.is_snippet_file_start:
            snippet_content = "...\n" + snippet_content
        if not self.is_snippet_file_end:
            snippet_content += "\n..."
        return f'''<snippet filepath="{self.file_path}" start="{self.start}" end="{self.end}">\n{snippet_content}\n</snippet>'''
        return f'''<snippet filepath="{self.file_path}" start="{self.start}" end="{self.end}">\n{self.get_snippet()}\n</snippet>'''

    _regex = r"""<review_comment>(?P<content>.*)<\/review_comment>"""
