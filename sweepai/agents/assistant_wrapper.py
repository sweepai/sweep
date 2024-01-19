import json
import os
import re
import time
from pathlib import Path
from typing import Callable

from loguru import logger
from openai import OpenAI
from openai.pagination import SyncCursorPage
from openai.types.beta.threads.thread_message import ThreadMessage
from pydantic import BaseModel

from sweepai.agents.assistant_functions import raise_error_schema
from sweepai.config.server import IS_SELF_HOSTED, OPENAI_API_KEY
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog

client = OpenAI(api_key=OPENAI_API_KEY, timeout=90) if OPENAI_API_KEY else None


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
    for attempt in range(num_retries):
        try:
            return call(*args, **kwargs, timeout=timeout)
        except Exception as e:
            logger.exception(f"Retry {attempt + 1} failed with error: {e}")
            error_message = str(e)
    raise Exception(
        f"Maximum retries reached. The call failed for call {error_message}"
    )


save_ticket_progress_type = Callable[[str, str, str], None]


class AssistantResponse(BaseModel):
    messages: SyncCursorPage[ThreadMessage]
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
]


def get_json_messages(
    thread_id: str,
    run_id: str,
    assistant_id: str,
):
    assistant = openai_retry_with_timeout(
        client.beta.assistants.retrieve,
        assistant_id=assistant_id,
    )
    messages = openai_retry_with_timeout(
        client.beta.threads.messages.list,
        thread_id=thread_id,
    )
    run_steps = openai_retry_with_timeout(
        client.beta.threads.runs.steps.list, run_id=run_id, thread_id=thread_id
    )
    system_message_json = {
        "role": "system",
        "content": assistant.instructions,
    }
    messages_json = [system_message_json]
    for message in messages:
        if message.role == "user":
            messages_json.append(
                {
                    "role": "user",
                    "content": message.content[0].text.value,
                }
            )
    for message_obj in list(run_steps.data)[:0:-1]:
        if message_obj.type == "message_creation":
            message_id = message_obj.step_details.message_creation.message_id
            thread_messages = openai_retry_with_timeout(
                client.beta.threads.messages.retrieve,
                message_id=message_id,
                thread_id=thread_id,
            )
            message_content = thread_messages.content[0].text.value
            messages_json.append(
                {
                    "role": "assistant",
                    "content": message_content,
                }
            )
            # TODO: handle annotations
        elif message_obj.type == "tool_calls":
            for tool_call in message_obj.step_details.tool_calls:
                if tool_call.type == "code_interpreter":
                    code_interpreter = tool_call.code_interpreter
                    input_ = code_interpreter.input
                    if not input_:
                        continue
                    input_content = f"Code interpreter input:\n```\n{input_}\n```"
                    messages_json.append(
                        {
                            "role": "assistant",
                            "content": input_content,
                        }
                    )
                    outputs = code_interpreter.outputs
                    output = outputs[0].logs if outputs else "__No output__"
                    output_content = f"Code interpreter output:\n```\n{output}\n```"
                    messages_json.append(
                        {
                            "role": "user",
                            "content": output_content,
                        }
                    )
                else:
                    function = tool_call.function
                    input_content = f"Function call of {function.name}:\n```\n{function.arguments}\n```"
                    messages_json.append(
                        {
                            "role": "assistant",
                            "content": input_content,
                        }
                    )
                    if function.output:
                        output_content = (
                            f"Function output:\n```\n{function.output}\n```"
                        )
                        messages_json.append(
                            {
                                "role": "user",
                                "content": output_content,
                            }
                        )
    return messages_json


def run_until_complete(
    thread_id: str,
    run_id: str,
    assistant_id: str,
    model: str = "gpt-4-1106-preview",
    chat_logger: ChatLogger | None = None,
    sleep_time: int = 3,
    max_iterations: int = 200,
    save_ticket_progress: save_ticket_progress_type | None = None,
):
    message_strings = []
    json_messages = []
    try:
        num_tool_calls_made = 0
        for i in range(max_iterations):
            run = openai_retry_with_timeout(
                client.beta.threads.runs.retrieve,
                thread_id=thread_id,
                run_id=run_id,
            )
            if run.status == "completed":
                logger.info(f"Run completed with {run.status}")
                break
            elif run.status in ("cancelled", "cancelling", "failed", "expired"):
                logger.info(f"Run completed with {run.status}")
                raise Exception(
                    f"Run failed assistant_id={assistant_id}, run_id={run_id}, thread_id={thread_id}"
                )
            elif run.status == "requires_action":
                num_tool_calls_made += 1
                if num_tool_calls_made > 15 and model.startswith("gpt-3.5"):
                    raise AssistantRaisedException(
                        "Too many tool calls made on GPT 3.5."
                    )
                tool_calls = [
                    tool_call
                    for tool_call in run.required_action.submit_tool_outputs.tool_calls
                ]
                if any(
                    [
                        tool_call.function.name == raise_error_schema["name"]
                        for tool_call in tool_calls
                    ]
                ):
                    arguments_parsed = json.loads(tool_calls[0].function.arguments)
                    raise AssistantRaisedException(arguments_parsed["message"])
                tool_outputs = []
                for tool_call in tool_calls:
                    try:
                        tool_call_arguments = re.sub(
                            r"\\+'", "", tool_call.function.arguments
                        )
                        function_input: dict = json.loads(tool_call_arguments)
                    except:
                        logger.warning(
                            f"Could not parse function arguments: {tool_call_arguments}"
                        )
                        tool_outputs.append(
                            {
                                "tool_call_id": tool_call.id,
                                "output": "FAILURE: Could not parse function arguments.",
                            }
                        )
                        continue
                    tool_output = yield tool_call.function.name, function_input
                    tool_output_formatted = {
                        "tool_call_id": tool_call.id,
                        "output": tool_output,
                    }
                    tool_outputs.append(tool_output_formatted)
                run = openai_retry_with_timeout(
                    client.beta.threads.runs.submit_tool_outputs,
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                )
            if save_ticket_progress is not None:
                save_ticket_progress(
                    assistant_id=assistant_id,
                    thread_id=thread_id,
                    run_id=run_id,
                )
            messages = openai_retry_with_timeout(
                client.beta.threads.messages.list,
                thread_id=thread_id,
            )
            current_message_strings = [
                message.content[0].text.value for message in messages.data
            ]
            if message_strings != current_message_strings and current_message_strings:
                logger.info(run.status)
                logger.info(current_message_strings[0])
                message_strings = current_message_strings
                json_messages = get_json_messages(
                    thread_id=thread_id,
                    run_id=run_id,
                    assistant_id=assistant_id,
                )
                if chat_logger is not None:
                    chat_logger.add_chat(
                        {
                            "model": model,
                            "messages": json_messages,
                            "output": message_strings[0],
                            "thread_id": thread_id,
                            "run_id": run_id,
                            "max_tokens": 1000,
                            "temperature": 0,
                        }
                    )
            else:
                if i % 5 == 0:
                    logger.info(run.status)
            time.sleep(sleep_time)
    except (KeyboardInterrupt, SystemExit):
        client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run_id)
        logger.warning(f"Run cancelled: {run_id}")
        raise SystemExit
    if save_ticket_progress is not None:
        save_ticket_progress(
            assistant_id=assistant_id,
            thread_id=thread_id,
            run_id=run_id,
        )
    for json_message in json_messages:
        logger.info(json_message["content"])
    return client.beta.threads.messages.list(
        thread_id=thread_id,
    )


def openai_assistant_call_helper(
    request: str,
    instructions: str | None = None,
    additional_messages: list[Message] = [],
    file_paths: list[str] = [],  # use either file_paths or file_ids
    uploaded_file_ids: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = "gpt-4-1106-preview",
    sleep_time: int = 3,
    chat_logger: ChatLogger | None = None,
    assistant_id: str | None = None,
    assistant_name: str | None = None,
    save_ticket_progress: save_ticket_progress_type | None = None,
):
    file_ids = [] if not uploaded_file_ids else uploaded_file_ids
    file_object = None
    if not file_ids:
        for file_path in file_paths:
            if not any(file_path.endswith(extension) for extension in allowed_exts):
                os.rename(file_path, file_path + ".txt")
                file_path += ".txt"
            file_object = client.files.create(
                file=Path(file_path), purpose="assistants"
            )
            file_ids.append(file_object.id)

    logger.debug(instructions)
    # always create new one
    assistant = openai_retry_with_timeout(
        client.beta.assistants.create,
        name=assistant_name,
        instructions=instructions,
        tools=tools,
        model=model,
    )
    thread = client.beta.threads.create()
    if file_ids:
        logger.info("Uploading files...")
    if request:
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=request,
            file_ids=file_ids,
        )
    if file_ids:
        logger.info("Files uploaded")
    for message in additional_messages:
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message.content,
        )
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
        instructions=instructions,
        model=model,
    )
    if len(tools) > 1:
        return run_until_complete(
            thread_id=thread.id,
            run_id=run.id,
            model=model,
            chat_logger=chat_logger,
            assistant_id=assistant.id,
            sleep_time=sleep_time,
            save_ticket_progress=save_ticket_progress,
        )
    for file_id in file_ids:
        client.files.delete(file_id=file_id)
    return (
        assistant.id,
        run.id,
        thread.id,
    )


# Split in two so it can be cached
def openai_assistant_call(
    request: str,
    instructions: str | None = None,
    additional_messages: list[Message] = [],
    file_paths: list[str] = [],
    uploaded_file_ids: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = "gpt-4-1106-preview",
    sleep_time: int = 3,
    chat_logger: ChatLogger | None = None,
    assistant_id: str | None = None,
    assistant_name: str | None = None,
    save_ticket_progress: save_ticket_progress_type | None = None,
):
    model = (
        "gpt-3.5-turbo-1106"
        if (chat_logger is None or chat_logger.use_faster_model())
        and not IS_SELF_HOSTED
        else "gpt-4-1106-preview"
    )
    posthog.capture(
        chat_logger.data.get("username") if chat_logger is not None else "anonymous",
        "call_assistant_api",
        {
            "query": request,
            "model": model,
            "username": chat_logger.data.get("username", "anonymous")
            if chat_logger is not None
            else "anonymous",
            "is_self_hosted": IS_SELF_HOSTED,
        },
    )
    retries = range(3)
    for _ in retries:
        try:
            response = openai_assistant_call_helper(
                request=request,
                instructions=instructions,
                additional_messages=additional_messages,
                file_paths=file_paths,
                uploaded_file_ids=uploaded_file_ids,
                tools=tools,
                model=model,
                sleep_time=sleep_time,
                chat_logger=chat_logger,
                assistant_id=assistant_id,
                assistant_name=assistant_name,
                save_ticket_progress=save_ticket_progress,
            )
            if len(tools) > 1:
                return response
            (assistant_id, run_id, thread_id) = response
            messages = client.beta.threads.messages.list(
                thread_id=thread_id,
            )
            return AssistantResponse(
                messages=messages,
                assistant_id=assistant_id,
                run_id=run_id,
                thread_id=thread_id,
            )
        except AssistantRaisedException as e:
            logger.warning(e.message)
        except Exception as e:
            logger.error(e)
            raise e
