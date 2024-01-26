import re
from typing import ClassVar, Generic, Literal, Type, TypeVar

import backoff
import tiktoken
from loguru import logger
from openai import OpenAI, RateLimitError
from pydantic import BaseModel

from sweepai.config.server import OPENAI_API_KEY

Self = TypeVar("Self", bound="RegexExtractModel")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class RegexExtractModel(BaseModel):
    _regex: ClassVar[str]

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        match = re.search(cls._regex, string, re.DOTALL)
        if match is None:
            raise Exception(f"Did not match {string} with pattern {cls._regex}")
        return cls(
            **{k: (v if v else None) for k, v in match.groupdict().items()},
            **kwargs,
        )


class Message(BaseModel):
    role: Literal["system"] | Literal["user"] | Literal["assistant"] | Literal[
        "function"
    ]
    content: str | None = None
    key: str | None = None

    def to_openai(self) -> str:
        obj = {
            "role": self.role,
            "content": self.content,
        }
        return obj


OpenAIModel = (
    Literal["gpt-3.5-turbo"]
    | Literal["gpt-3.5-turbo-1106"]
    | Literal["gpt-3.5-turbo-16k"]
    | Literal["gpt-4"]
    | Literal["gpt-4-0613"]
    | Literal["gpt-4-1106-preview"]
    | Literal["gpt-4-0125-preview"]
    | Literal["gpt-4-32k"]
)

model_to_max_tokens = {
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-3.5-turbo-16k": 16385,
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-1106-preview": 128000,
    "gpt-4-0125-preview": 128000,
    "gpt-4-32k": 32000,
}


class SweepChatGPT(BaseModel):
    messages: list[Message] = []
    model: OpenAIModel = "gpt-4-0613"
    temperature: float = 0.1

    def chat(
        self,
        content: str,
        model: OpenAIModel | None = None,
        message_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.messages.append(Message(role="user", content=content, key=message_key))
        self.messages.append(
            Message(
                role="assistant",
                content=self.call_openai(
                    model=model or self.model,
                    temperature=temperature or self.temperature,
                    requested_max_tokens=max_tokens,
                ),
                key=message_key,
            )
        )
        return self.messages[-1].content

    def call_openai(
        self,
        model: OpenAIModel | None = None,
        temperature: float | None = 0.1,
        requested_max_tokens: int | None = None,
    ):
        count_tokens = lambda text: len(
            tiktoken.encoding_for_model(model).encode(text, disallowed_special=())
        )
        messages_length = sum(
            [count_tokens(message.content or "") for message in self.messages]
        )
        computed_max_tokens = (model_to_max_tokens[model] - int(messages_length)) - 50
        messages_dicts = [self.messages_dicts[0]]
        for message_dict in self.messages_dicts[:1]:
            if message_dict["role"] == messages_dicts[-1]["role"]:
                messages_dicts[-1]["content"] += "\n" + message_dict["content"]
            messages_dicts.append(message_dict)

        computed_max_tokens = (
            min(computed_max_tokens, 4096)
            if model == "gpt-4-0125-preview"
            else computed_max_tokens
        )
        max_tokens = (
            min(requested_max_tokens, computed_max_tokens)
            if requested_max_tokens
            else computed_max_tokens
        )

        @backoff.on_exception(
            backoff.expo,
            RateLimitError,
            max_tries=16,
            jitter=backoff.random_jitter,
        )
        def backoff_openai_call():
            try:
                # TODO: The 'openai.api_base' option isn't read in the client API. You will need to pass it when you instantiate the client, e.g. 'OpenAI(api_base="https://api.openai.com/v1")'
                # openai.api_base = "https://api.openai.com/v1"

                openai_response = client.chat.completions.create(
                    model=model,
                    messages=self.messages_dicts,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return openai_response.choices[0].message.content
            except RateLimitError as e:
                raise e
            except Exception as e:
                logger.error(e)
                raise e

        return backoff_openai_call()

    @property
    def messages_dicts(self):
        return [message.to_openai() for message in self.messages]

    def undo_last_message(self):
        if len(self.messages) > 0:
            self.messages.pop()
        return self.messages


R = TypeVar("R", bound="RegexExtractModel")


class SweepAgent(SweepChatGPT, Generic[R]):
    regex_extract_model: ClassVar[Type[R]] = RegexExtractModel
    system_prompt: ClassVar[str] = ""
    user_prompt: ClassVar[str] = ""

    def handle_task(
        self,
        system_prompt_args: dict[str, str] = {},
        user_prompt_args: dict[str, str] = {},
        **kwargs,
    ) -> R:
        if self.system_prompt:
            formatted_system_prompt = self.system_prompt.format(**system_prompt_args)
            self.messages.append(
                Message(role="system", content=formatted_system_prompt)
            )
        formatted_prompt = self.user_prompt.format(**user_prompt_args)
        chatgpt_response = self.chat(formatted_prompt)
        serialized_response_object = self.regex_extract_model.from_string(
            chatgpt_response
        )
        return serialized_response_object

    def handle_task_with_retries(
        self,
        system_prompt_args: dict[str, str],
        user_prompt_args: dict[str, str],
        **kwargs,
    ) -> R:
        if self.system_prompt:
            formatted_system_prompt = self.system_prompt.format(**system_prompt_args)
            self.messages.append(
                Message(role="system", content=formatted_system_prompt)
            )
        formatted_prompt = self.user_prompt.format(**user_prompt_args)
        if self.regex_extract_model:
            num_retries = kwargs.get("num_retries", 3)
            for _ in range(num_retries):
                chatgpt_response = self.chat(formatted_prompt)
                try:
                    serialized_response_object = self.regex_extract_model.from_string(
                        chatgpt_response
                    )
                except Exception as e:
                    self.messages.append(
                        Message(
                            role="user",
                            content=f"The previous response failed to parse using the pattern: {self.regex_extract_model._regex}. Please try again.",
                        )
                    )
                    logger.error(e)
                    continue
                return serialized_response_object
        chatgpt_response = self.chat(formatted_prompt)
        return chatgpt_response


if __name__ == "__main__":

    class Locations(RegexExtractModel):
        locations_string: str
        _regex = r"<locations>(?P<locations_string>.*?)</locations>"

        @property
        def locations(self):
            return [
                location for location in self.locations_string.split("\n") if location
            ]

    class FindLocationsAgent(SweepAgent):
        regex_extract_model = Locations
        system_prompt = "You are a geographer."
        user_prompt = "Tell me the midpoint between {first_location} and {second_location}. Then provide four cities near that midpoint formatted using <locations>\nCity1\nCity2\nCity3\nCity4\n</locations> tags."

    find_locations_agent = FindLocationsAgent()
    location_obj = find_locations_agent.handle_task(
        user_prompt_args={"first_location": "NYC", "second_location": "LA"},
    )
    print(location_obj.locations)
