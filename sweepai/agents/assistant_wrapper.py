import json
from typing import Any, Callable, Optional

from loguru import logger
from openai.pagination import SyncCursorPage
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from pydantic import BaseModel

def openai_retry_with_timeout(call, *args, num_retries=3, timeout=5, **kwargs):
    """
    Pass any OpenAI client call and retry it num_retries times, incorporating timeout into the call.

    Usage:
    run = openai_retry_with_timeout(client.beta.threads.runs.submit_tool_outputs, thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs, num_retries=3, timeout=10)

    Parameters:
    call (callable): The OpenAI client call to be retried.
    *args: Positional arguments for the callable.
    num_retries (int): The number of times to retry the call.
    timeout (int): The timeout value to be applied to the call.
    **kwargs: Keyword arguments for the callable.

    Returns:
    The result of the OpenAI client call.
    """
    error_message = None
    e = None
    for attempt in range(num_retries):
        try:
            return call(*args, **kwargs, timeout=timeout)
        except Exception as e_:
            logger.exception(f"Retry {attempt + 1} failed with error: {e_}")
            error_message = str(e_)
            e = e_
    if e:
        raise Exception(
            f"Maximum retries reached. The call failed for call {error_message}"
        ) from e
    else:
        raise Exception(
            f"Maximum retries reached. The call failed for call {error_message}"
        )


def fix_tool_calls(tool_calls: Optional[list[ChatCompletionMessageToolCall]]):
    if tool_calls is None:
        return

    fixed_tool_calls = []

    for tool_call in tool_calls:
        current_function = tool_call.function.name
        try:
            function_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            logger.error(
                f"Error: could not decode function arguments: {tool_call.function.args}"
            )
            fixed_tool_calls.append(tool_call)
            continue
        if current_function in ("parallel", "multi_tool_use.parallel"):
            for _fake_i, _fake_tool_use in enumerate(function_args["tool_uses"]):
                _function_args = _fake_tool_use["parameters"]
                _current_function = _fake_tool_use["recipient_name"]
                if _current_function.startswith("functions."):
                    _current_function = _current_function[len("functions.") :]

                fixed_tc = ChatCompletionMessageToolCall(
                    id=f"{tool_call.id}_{_fake_i}",
                    type="function",
                    function=Function(
                        name=_current_function, arguments=json.dumps(_function_args)
                    ),
                )
                fixed_tool_calls.append(fixed_tc)
        else:
            fixed_tool_calls.append(tool_call)

    return fixed_tool_calls


save_ticket_progress_type = Callable[[str, str, str], None]


class AssistantResponse(BaseModel):
    messages: SyncCursorPage[Any]
    assistant_id: str
    run_id: str
    thread_id: str


allowed_exts = [
    "c",
    "cpp",
    "csv",
    "docx",
    "html",
    "java",
    "json",
    "md",
    "pdf",
    "php",
    "pptx",
    "py",
    "rb",
    "tex",
    "txt",
    "css",
    "jpeg",
    "jpg",
    "js",
    "gif",
    "png",
    "tar",
    "ts",
    "xlsx",
    "xml",
    "zip",
    "elm",
]