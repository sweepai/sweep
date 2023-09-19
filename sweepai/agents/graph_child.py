import re
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel, Snippet

system_prompt = """You are a genius engineer tasked with solving the following GitHub issue. 
Some relevant_snippets_from_repo have been provided. Assume any changes relevant to those snippets have been taken care of.
Determine whether changes in the new_file are necessary. 
If code changes need to be in this file, provide the relevant_new_snippet and the changes_for_new_file. 
Extract the code you deem necessary, and then describe the necessary code changes. Otherwise leave both sections blank.

# Extraction

Include only the relevant snippet that provides enough detail to solve the issue: Keep the 
relevant_snippet as small as possible. When writing the code changes keep in mind the user can read the metadata and the relevant snippets.

<code_analysis>
{thought about potentially relevant snippet and its relevance to the issue}
...
</code_analysis>

<relevant_new_snippet>
{relevant snippet from the new_file in the format file_path:start_idx-end_idx}
...
</relevant_new_snippet>

<changes_for_new_file>
{Detailed natural language instructions of modifications to be made in new_file.}
</changes_for_new_file>
"""

graph_user_prompt = """
<metadata>
{issue_metadata}
</metadata>

{previous_snippets}

<all_symbols_and_files>
{all_symbols_and_files}</all_symbols_and_files>

<new_file file_path=\"{file_path}\" entities=\"{entities}\">
{code}
</new_file>

Provide the relevant snippets and changes from the new_file above.
"""

class GraphContextAndPlan(RegexMatchableBaseModel):
    relevant_new_snippet: list[Snippet]
    changes_for_new_file: str
    file_path: str
    entities: str = None

    @classmethod
    def from_string(cls, string: str, file_path:str, **kwargs):
        snippets_pattern = r"""<relevant_new_snippet>(\n)?(?P<relevant_new_snippet>.*)</relevant_new_snippet>"""
        plan_pattern = r"""<changes_for_new_file>(\n)?(?P<changes_for_new_file>.*)</changes_for_new_file>"""
        snippets_match = re.search(snippets_pattern, string, re.DOTALL)
        relevant_new_snippet_match = None
        changes_for_new_file = ""
        relevant_new_snippet = []
        if not snippets_match:
            return cls(relevant_new_snippet=relevant_new_snippet, changes_for_new_file=changes_for_new_file, file_path=file_path, **kwargs)
        relevant_new_snippet_match = snippets_match.group("relevant_new_snippet")
        for raw_snippet in relevant_new_snippet_match.split("\n"):
            if ":" not in raw_snippet:
                continue
            generated_file_path, lines = raw_snippet.split(":", 1)
            generated_file_path, lines = generated_file_path.strip(), lines.split()[0].strip() # second one accounts for trailing text like "1-10 (message)"
            if generated_file_path != file_path:
                continue
            if "-" not in lines:
                continue
            start, end = lines.split("-", 1)
            start, end = extract_int(start), extract_int(end)
            if start is None or end is None:
                continue
            start = int(start)
            end = int(end) - 1
            end = min(end, start + 200)
            snippet = Snippet(file_path=file_path, start=start, end=end, content="")
            relevant_new_snippet.append(snippet)
        plan_match = re.search(plan_pattern, string, re.DOTALL)
        if plan_match:
            changes_for_new_file = plan_match.group("changes_for_new_file").strip()
        return cls(
            relevant_new_snippet=relevant_new_snippet, changes_for_new_file=changes_for_new_file, file_path=file_path, **kwargs
        )

    def __str__(self) -> str:
        return f"{self.relevant_new_snippet}\n{self.changes_for_new_file}"
    
class GraphChildBot(ChatGPT):
    def code_plan_extraction(
        self, code, file_path, entities, issue_metadata, previous_snippets, all_symbols_and_files
    ) -> GraphContextAndPlan:
        self.messages = [
            Message(
                role="system",
                content=system_prompt,
                key="system",
            )
        ]
        code_with_line_numbers = extract_python_span(code, entities)

        user_prompt = graph_user_prompt.format(
            code=code_with_line_numbers,
            file_path=file_path,
            entities=entities,
            issue_metadata=issue_metadata,
            previous_snippets=previous_snippets,
            all_symbols_and_files=all_symbols_and_files,
        )
        self.model = (
            "gpt-4-32k-0613"
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else "gpt-3.5-turbo-16k-0613"
        )
        response = self.chat(user_prompt)
        graph_plan = GraphContextAndPlan.from_string(response, file_path=file_path)
        graph_plan.entities = entities
        return graph_plan

def extract_int(s):
    match = re.search(r"\d+", s)
    if match:
        return int(match.group())
    return None

def extract_python_span(code, entities):
    # Identify lines where entity is mentioned
    mentioned_lines = []
    lines = code.split("\n")
    for i, line in enumerate(lines):
        for entity in entities:
            if entity in line:
                mentioned_lines.append(i)
    # Calculate the window to show
    window_size = 100
    start_window = max(0, min(mentioned_lines))
    end_window = max(mentioned_lines)

    # Extend end_window to the next line with no indent
    for i in range(end_window + 1, len(lines)):
        if lines[i].strip() and not lines[i].startswith(" "):
            end_window = i
            break
    else:
        end_window = len(lines)

    if end_window - start_window < 2:
        end_window = start_window + window_size

    # Extract lines in the window and mark where entity is mentioned
    code_with_line_numbers = ""
    for i in range(start_window, end_window):
        line = lines[i]
        mentioned_entities = [entity for entity in entities if entity in line]
        if len(mentioned_entities) == 1:
            code_with_line_numbers += f"{i + 1} {line}" + f" <- {mentioned_entities[0]} is mentioned here\n"
        elif len(mentioned_entities) > 1:
            mentioned_entities = ", ".join(mentioned_entities)
            code_with_line_numbers += f"{i + 1} {line}" + f" <- {mentioned_entities} are mentioned here\n"
        else:
            code_with_line_numbers += f"{i + 1} {line}\n"
    code_with_line_numbers = code_with_line_numbers.strip()
    return code_with_line_numbers

if __name__ == "__main__":
    file = r"""import json
from copy import deepcopy
import time
from typing import Any, Iterator, Literal
import traceback

import anthropic
import backoff
from pydantic import BaseModel

from logn import logger
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.utils import Tiktoken
from sweepai.core.entities import Message, Function, SweepContext
from sweepai.core.prompts import system_message_prompt, repo_description_prefix_prompt
from sweepai.utils.chat_logger import ChatLogger
from sweepai.config.client import get_description
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.openai_proxy import OpenAIProxy
from sweepai.config.server import (
    OPENAI_USE_3_5_MODEL_ONLY,
    OPENAI_DO_HAVE_32K_MODEL_ACCESS,
)
from sweepai.utils.event_logger import posthog
import openai

openai_proxy = OpenAIProxy()

AnthropicModel = (
    Literal["claude-v1"]
    | Literal["claude-v1.3-100k"]
    | Literal["claude-instant-v1.1-100k"]
)
OpenAIModel = (
    Literal["gpt-3.5-turbo"]
    | Literal["gpt-4"]
    | Literal["gpt-4-0613"]
    | Literal["gpt-3.5-turbo-16k"]
    | Literal["gpt-3.5-turbo-16k-0613"]
    | Literal["gpt-4-32k"]
    | Literal["gpt-4-32k-0613"]
)

ChatModel = OpenAIModel | AnthropicModel
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
count_tokens = Tiktoken().count


def format_for_anthropic(messages: list[Message]) -> str:
    if len(messages) > 1:
        new_messages: list[Message] = [
            Message(
                role="system", content=messages[0].content + "\n" + messages[1].content
            )
        ]
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
    model: ChatModel = (
        "gpt-4-32k-0613" if OPENAI_DO_HAVE_32K_MODEL_ACCESS else "gpt-4-0613"
    )
    chat_logger: ChatLogger | None
    human_message: HumanMessagePrompt | None = None
    file_change_paths: list[str] = []
    sweep_context: SweepContext | None = None
    cloned_repo: ClonedRepo | None = (None,)

    @classmethod
    def from_system_message_content(
        cls,
        human_message: HumanMessagePrompt,
        is_reply: bool = False,
        chat_logger=None,
        sweep_context=None,
        cloned_repo: ClonedRepo | None = None,
        **kwargs,
    ) -> Any:
        content = system_message_prompt
        repo = kwargs.get("repo")
        if repo:
            logger.info(f"Repo: {repo}")
            repo_description = get_description(repo)
            if repo_description:
                logger.info(f"Repo description: {repo_description}")
                content += f"{repo_description_prefix_prompt}\n{repo_description}"
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
        cls, prompt_string, chat_logger: ChatLogger, **kwargs
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
        temperature=temperature,
    ):
        self.messages.append(Message(role="user", content=content, key=message_key))
        model = model or self.model
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

    def call_openai(
        self,
        model: ChatModel | None = None,
        temperature=temperature,
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
                    except Exception as e:
                        logger.warning(e)
                return output
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
                logger.warning(
                    f"{tickets_count} tickets found in MongoDB, using {model}"
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
        return self.messages"""
    
    print(extract_int("10, 10-11 (message)"))
    span = extract_python_span(file, "ChatGPT")
    print(span)