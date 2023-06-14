import re
from typing import ClassVar, Literal, Self, Type

import openai
from loguru import logger
from pydantic import BaseModel

from src.core.prompts import system_message_prompt


ChatModel = Literal["gpt-3.5-turbo"] | Literal["gpt-4"]
model_to_max_tokens = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8096,
}


class Message(BaseModel):
    role: Literal["system"] | Literal["user"] | Literal["assistant"]
    content: str


class ChatGPT(BaseModel):
    messages: list[Message] = [
        Message(
            role="system",
            content=system_message_prompt,
        )
    ]
    prev_message_states: list[list[Message]] = []
    model: ChatModel = "gpt-4"

    @classmethod
    def from_system_message_content(cls, content: str, **kwargs) -> Self:
        return cls(messages=[Message(role="system", content=content)], **kwargs)

    def chat(self, content: str, model: ChatModel | None = None):
        self.prev_message_states.append(self.messages)
        self.messages.append(Message(role="user", content=content))
        # response = call_chatgpt(self.messages_dicts, model=model)
        response = self.call_openai(model=model)
        self.messages.append(Message(role="assistant", content=response))
        return self.messages[-1].content

    def call_openai(self, model: ChatModel | None = None):
        if model is None:
            model = self.model
        messages_length = (
            sum([message.content.count(" ") for message in self.messages]) * 1.5
        )
        max_tokens = model_to_max_tokens[model] - int(messages_length) - 1000
        messages_raw = "\n".join([message.content for message in self.messages])
        logger.info(f"Input:\n{messages_raw}")
        result = (
            openai.ChatCompletion.create(
                model=model,
                messages=self.messages_dicts,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            .choices[0]
            .message["content"]
        )
        logger.info(f"Output:\n{result}")
        return result

    @property
    def messages_dicts(self):
        return [message.dict() for message in self.messages]

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
            raise RegexMatchError("Did not match")
        return cls(
            **{k: (v if v else "").strip() for k, v in match.groupdict().items()},
            **kwargs,
        )


class FilesToChange(RegexMatchableBaseModel):
    files_to_modify: str
    files_to_create: str
    _regex = (
        r"""Thoughts:.*Create:(?P<files_to_create>.*)Modify:(?P<files_to_modify>.*)"""
    )


class FileChangeRequest(RegexMatchableBaseModel):
    filename: str
    instructions: str
    change_type: Literal["modify"] | Literal["create"]
    _regex = r"""`(?P<filename>.*)`:(?P<instructions>.*)"""


class FileChange(RegexMatchableBaseModel):
    commit_message: str
    code: str
    _regex = r"""Commit Message:(?P<commit_message>[^`]*)```(?P<code>.*)```"""


class PullRequest(RegexMatchableBaseModel):
    title: str
    branch_name: str
    content: str
    _regex = r"""Title:(?P<title>.*)Branch Name:(?P<branch_name>.*)Content:.*```(?P<content>.*)```"""
