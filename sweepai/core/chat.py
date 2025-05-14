from math import inf
import os
import re
import textwrap
import time
import traceback
from typing import Any, Callable, Iterator, Literal

from anthropic import Anthropic, BadRequestError, AnthropicBedrock, Stream
from anthropic.types import MessageStreamEvent
from openai import OpenAI
import backoff
from loguru import logger
from pydantic import BaseModel

from sweepai.config.server import (
    ALTERNATE_AWS,
    ANTHROPIC_AVAILABLE,
    AWS_ACCESS_KEY,
    AWS_REGION,
    AWS_SECRET_KEY,
    DEFAULT_GPT4_MODEL,
    PAREA_API_KEY
)
from sweepai.core.entities import Message
from sweepai.core.prompts import system_message_prompt
from sweepai.core.viz_utils import save_messages_for_visualization
from sweepai.logn.cache import file_cache
from sweepai.utils.anthropic_client import sanitize_anthropic_messages
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.image_utils import create_message_with_images
from sweepai.utils.openai_proxy import OpenAIProxy
from sweepai.utils.str_utils import truncate_text_based_on_stop_sequence
from sweepai.utils.tiktoken_utils import Tiktoken
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
    | Literal["gpt-4-turbo-2024-04-09"]
    | Literal["gpt-4-turbo"]
)

AnthropicModel = (
    Literal["claude-3-haiku-20240307"]
    | Literal["claude-3-sonnet-20240229"]
    | Literal["claude-3-5-sonnet-20240620"]
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
    "gpt-4o": 128000,
    "claude-v1": 9000,
    "claude-v1.3-100k": 100000,
    "claude-instant-v1.3-100k": 100000,
    "anthropic.claude-3-haiku-20240229-v1:0": 200000,
    "anthropic.claude-3-sonnet-20240229-v1:0": 200000,
    "claude-3-opus-20240229": 200000,
    "claude-3-sonnet-20240229": 200000,
    "claude-3-5-sonnet-20240620": 200000,
    "claude-3-haiku-20240307": 200000,
    "gpt-3.5-turbo-16k-0613": 16000,
}
default_temperature = 0.1

MAX_CHARS = 32000

def ensure_additional_messages_length(additional_messages: list[Message]) -> list[Message]:
    for i, additional_message in enumerate(additional_messages):
        if len(additional_message.content) > MAX_CHARS:
            wrapper = textwrap.TextWrapper(width=MAX_CHARS, replace_whitespace=False)
            new_messages = wrapper.wrap(additional_message.content)
            # replace the original message with the broken up messages
            for j, new_message in enumerate(new_messages):
                if j == 0:
                    additional_messages[i] = Message(
                        role=additional_message.role,
                        content=new_message,
                    )
                else:
                    additional_messages.insert(
                        i + j,
                        Message(
                            role=additional_message.role,
                            content=new_message,
                        ),
                    )
    return additional_messages

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
    "make_change": ["justification", "file_name", "original_code", "new_code", "replace_all"],
    "create_file": ["justification", "file_name", "new_code"],
    "submit_task": ["sources", "justification", "answer"],
    "search_codebase": ["query", "question", "include_docs", "include_tests"],
    "semantic_search": ["query", "question", "include_docs", "include_tests"],
    "ripgrep": ["query"],
}

# returns a dictionary of the tool call parameters, assumes correct
def parse_function_call_parameters(tool_call_contents: str, parameters: list[str]) -> dict[str, Any]:
    tool_args = {}
    for param in parameters:
        param_regex = rf'<{param}>(?P<{param}>.*?)<\/{param}>'
        match = re.search(param_regex, tool_call_contents, re.DOTALL)
        if match:
            param_contents = match.group(param)
            tool_args[param] = param_contents
    return tool_args

# parse llm response for tool calls in xml format
def parse_function_calls(response_contents: str) -> list[dict[str, str]]:
    tool_calls = []
    # first get all tool calls
    for tool_name in tool_call_parameters.keys():
        tool_call_regex = rf'<{tool_name}>(?P<function_call>.*?)<\/{tool_name}>'
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

# go through each message and see if we need to update it to include images or not
def add_images_to_messages(message_dicts: list[dict[str, str]], images: list[tuple[str, str, str]], use_openai: bool = False):
    if not images:
        return message_dicts
    new_message_dicts = []
    for message in message_dicts:
        new_message = create_message_with_images(message, images, use_openai=use_openai)
        new_message_dicts.append(new_message)
    return new_message_dicts

class ChatGPT(MessageList):
    prev_message_states: list[list[Message]] = []
    model: ChatModel = DEFAULT_GPT4_MODEL
    chat_logger: ChatLogger | None = None
    file_change_paths: list[str] = []
    temperature: float = default_temperature

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_system_message_string(
        cls, prompt_string: str, chat_logger: ChatLogger | None = None, **kwargs
    ) -> Any:
        return cls(
            messages=[Message(role="system", content=prompt_string, key="system")],
            chat_logger=chat_logger,
            **kwargs,
        )

    def chat(
        self,
        content: str,
        model: ChatModel | None = None,
        message_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop_sequences: list[str] = [],
    ):
        self.messages.append(Message(role="user", content=content, key=message_key)) if content else None # supports calling assistant again
        model = model or self.model
        temperature = temperature or self.temperature or default_temperature
        new_content = self.call_openai(
            model=model,
            temperature=temperature,
            requested_max_tokens=max_tokens,
            stop_sequences=stop_sequences,
        )
        self.messages.append(
            Message(
                role="assistant",
                content=new_content,
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
                    except Exception as e2:
                        logger.warning(e2)
                return output
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
        verbose: bool = True,
        images: list[tuple[str, str, str]] | None = None,
        stream: bool = False,
        seed: int | None = None,
    ) -> str | Iterator[str]:
        if not os.environ.get("ANTHROPIC_API_KEY") and not ANTHROPIC_AVAILABLE:
            use_openai = True
        if use_openai:
            OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
            assert OPENAI_API_KEY
            # self.model = 'gpt-4-turbo'
            self.model = 'gpt-4o'
        else:
            ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
            assert ANTHROPIC_API_KEY
            self.model = model
        if content:
            self.messages.append(Message(role="user", content=content, key=message_key))
        if assistant_message_content:
            self.messages.append(Message(role="assistant", content=assistant_message_content))
        temperature = temperature or self.temperature or default_temperature
        if verbose:
            # messages_string_to_log = '\n\n'.join([message.content for message in self.messages])
            if use_openai:
                logger.debug(f"Calling openai with model {model}\nInput:\n{content}")
            else:
                logger.debug(f"Calling anthropic with model {model}\nInput:\n{content}")
        system_message = "\n\n".join([message.content for message in self.messages if message.role == "system"])
        content = ""
        e = None
        NUM_ANTHROPIC_RETRIES = 6
        use_aws = True
        hit_content_filtering = False
        if stream:
            def llm_stream():
                model = self.model
                streamed_text = ""
                if use_openai:
                    client = OpenAI()
                    response = client.chat.completions.create(
                        model=model,
                        messages=self.messages_dicts,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stream=True,
                    )
                    streamed_text = ""
                    for chunk in response:
                        new_content = chunk.choices[0].delta.content
                        if new_content:
                            streamed_text += new_content
                        print(new_content, end="", flush=True)
                        yield new_content
                        if chunk.choices[0].finish_reason == "stop":
                            break
                        for stop_sequence in stop_sequences:
                            if stop_sequence in streamed_text:
                                response = truncate_text_based_on_stop_sequence(streamed_text, stop_sequences)
                                try:
                                    save_messages_for_visualization(
                                        self.messages + [Message(role="assistant", content=response)],
                                        use_openai=use_openai,
                                        model_name=model
                                    )
                                except Exception as e:
                                    logger.warning(f"Error saving messages for visualization: {e}")
                                return
                else:
                    if ANTHROPIC_AVAILABLE and use_aws:
                        if "anthropic" not in model:
                            model = f"anthropic.{model}-v1:0"
                        client = AnthropicBedrock(
                            aws_access_key=AWS_ACCESS_KEY,
                            aws_secret_key=AWS_SECRET_KEY,
                            aws_region=AWS_REGION,
                        )
                    else:
                        client = Anthropic(api_key=ANTHROPIC_API_KEY)
                    start_time = time.time()
                    message_dicts = [
                        {
                            "role": message.role,
                            "content": message.content,
                        } for message in self.messages if message.role != "system"
                    ]
                    message_dicts = sanitize_anthropic_messages(message_dicts)

                    start_time = time.time()
                    print(f"In queue with model {model}...")
                    response: Stream[MessageStreamEvent] = client.messages.create(
                        model=model,
                        messages=message_dicts,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system_message,
                        stream=True
                    )
                    streamed_text = ""
                    for event in response:
                        match event.type:
                            case "message_start":
                                print(f"Starting stream with {event.message.usage.input_tokens} input tokens in {time.time() - start_time:.2f}s")
                            case "content_block_delta":
                                streamed_text += event.delta.text
                                print(event.delta.text, end="", flush=True)
                                yield event.delta.text
                                if any(stop_sequence in streamed_text for stop_sequence in stop_sequences):
                                    print(f"Stop sequence hit after {time.time() - start_time:.2f}s")
                                    return truncate_text_based_on_stop_sequence(streamed_text, stop_sequences)
                            case "content_block_stop":
                                print()
                                break
                            case _:
                                print(event)
                    print(f"Streamed {len(streamed_text)} characters in {time.time() - start_time:.2f}s")
                response = streamed_text
                try:
                    save_messages_for_visualization(
                        self.messages + [Message(role="assistant", content=response)],
                        use_openai=use_openai,
                        model_name=model
                    )
                except Exception as e:
                    logger.warning(f"Error saving messages for visualization: {e}")
                return response
            return llm_stream()
        for i in range(NUM_ANTHROPIC_RETRIES):
            try:
                @file_cache(redis=True, ignore_contents=True) # must be in the inner scope because this entire function manages state
                def call_anthropic(
                    message_dicts: list[dict[str, str]], 
                    system_message: str = system_message, 
                    model: str = model,
                    use_openai: bool = use_openai,
                    use_aws: bool = True,
                    seed: int = seed,
                ) -> str: # add system message and model to cache
                    if use_openai:
                        client = OpenAI()
                    else:
                        if ANTHROPIC_AVAILABLE and use_aws:
                            if "anthropic" not in model:
                                model = f"anthropic.{model}-v1:0"
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
                        print("Starting OpenAI stream")
                        response = client.chat.completions.create(
                            model=model,
                            messages=self.messages_dicts,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            stream=True,
                        )
                        streamed_text = ""
                        text = ""
                        for chunk in response:
                            new_content = chunk.choices[0].delta.content
                            text += new_content if new_content else ""
                            if new_content:
                                print(new_content, end="", flush=True)
                                streamed_text += new_content
                                for stop_sequence in stop_sequences:
                                    if stop_sequence in streamed_text:
                                        return truncate_text_based_on_stop_sequence(streamed_text, stop_sequences)
                        print() # clear the line
                        response = truncate_text_based_on_stop_sequence(streamed_text, stop_sequences)
                        return text
                    else:
                        verbose = True
                        start_time = time.time()
                        if verbose:
                            print(f"In queue with model {model}...")
                        response: Stream[MessageStreamEvent] = client.messages.create(
                            model=model,
                            messages=message_dicts,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system=system_message,
                            stream=True
                        )
                        streamed_text = ""
                        for event in response:
                            match event.type:
                                case "message_start":
                                    print(f"Starting stream with {event.message.usage.input_tokens} input tokens in {time.time() - start_time:.2f}s")
                                case "content_block_delta":
                                    streamed_text += event.delta.text
                                    print(event.delta.text, end="", flush=True)
                                    if any(stop_sequence in streamed_text for stop_sequence in stop_sequences):
                                        print(f"Stop sequence hit after {time.time() - start_time:.2f}s")
                                        return truncate_text_based_on_stop_sequence(streamed_text, stop_sequences)
                                case "content_block_stop":
                                    print()
                                    break
                                case _:
                                    print(event)
                        print(f"Streamed {len(streamed_text)} characters in {time.time() - start_time:.2f}s")
                        response = streamed_text

                        if verbose:
                            print("Done streaming results!")
                        # manually chop off text after any stop tokens because including stop sequences makes the llms lazy
                        response = truncate_text_based_on_stop_sequence(response, stop_sequences)
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
                # need to modify message dicts if we have images
                if images:
                    message_dicts = add_images_to_messages(message_dicts, images, use_openai=use_openai)
                content = call_anthropic(message_dicts, self.messages[0].content, self.model, use_openai=use_openai, use_aws=use_aws, seed=seed)
                break
            except BadRequestError as e_:
                e = e_ # sometimes prompt is too long
                if not ALTERNATE_AWS:
                    raise e_
                elif hit_content_filtering: # hit it twice, raise error
                    raise e_
                else:
                    hit_content_filtering = True # stop using anthropic
            except Exception as e_:
                logger.exception(e_)
                e = e_
                time.sleep(4 * 1.75 ** i) # faster debugging
                if ALTERNATE_AWS: # alternate between aws and anthropic (for load balancing only)
                    use_aws = not use_aws and not hit_content_filtering
        else:
            raise Exception(f"Anthropic call failed:\n{e}") from e
        self.messages.append(
            Message(
                role="assistant",
                content=content,
                key=message_key,
            )
        )
        if verbose:
            logger.debug(f'{"Openai" if use_openai else "Anthropic"} response: {self.messages[-1].content}')
        try:
            save_messages_for_visualization(messages=self.messages, use_openai=use_openai, model_name=model)
        except Exception as e:
            logger.exception(f"Failed to save messages for visualization due to {e}")
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

def call_llm(
    system_prompt: str,
    user_prompt: str,
    params: dict = {},
    *args,
    **kwargs,
):
    chat_gpt = ChatGPT.from_system_message_string(
        prompt_string=system_prompt,
    )

    if params:
        user_prompt = user_prompt.format(**params)

    return chat_gpt.chat_anthropic(
        user_prompt,
        *args,
        **kwargs,
    )

def continuous_llm_calls(
    chat_gpt: ChatGPT,
    *args,
    stop_sequences: list[str] = ["</plan>"],
    MAX_CALLS = 10,
    use_openai: bool = False,
    response_cleanup: Callable[[str], str] = lambda x: x,
    **kwargs    
):
    response: str = chat_gpt.chat_anthropic(
        use_openai=use_openai,
        *args,
        **kwargs
    )
    next_response = response
    num_calls = 0
    while not any(token in response for token in stop_sequences) \
        and len(next_response) > 3.5 * 4096 * 0.8 \
        and num_calls < MAX_CALLS: # 80% of max tokens
        last_line_index = response.rfind("\n")
        content = ""
        if use_openai:
            last_block_original_code = response.rfind("<original_code>\n") + len("<original_code>\n")
            last_block_new_code = response.rfind("<new_code>\n") + len("<new_code>\n")
            last_block = max(last_block_original_code, last_block_new_code)
            if last_line_index - last_block < 2500:
                last_line_index = last_block
        response = response[:last_line_index].rstrip()
        last_k_lines = response.split("\n")[-10:]
        if use_openai:
            content = "Continue generating. DO NOT restart from scratch. Here is the last part of your response to continue from:\n\n" + "\n".join(last_k_lines)
        chat_gpt.messages[-1].content = response_cleanup(response)
        # ask for a second response
        try:
            if "content" in kwargs:
                kwargs.pop("content")
            next_response: str = chat_gpt.chat_anthropic(
                use_openai=use_openai,
                *args,
                **kwargs,
                content=content
            )
            next_response = response_cleanup(next_response)
            # we can simply concatenate the responses
            response += next_response
        except Exception as e:
            logger.error(f"Failed to get second response due to {e}")
        num_calls += 1
    return response
