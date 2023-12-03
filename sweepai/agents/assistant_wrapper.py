import json
import os
import time
from pathlib import Path

from loguru import logger
from openai import OpenAI
from openai.pagination import SyncCursorPage
from openai.types.beta.threads.thread_message import ThreadMessage
from pydantic import BaseModel

from sweepai.agents.assistant_functions import raise_error_schema
from sweepai.config.server import OPENAI_API_KEY
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


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
    assistant = client.beta.assistants.retrieve(assistant_id=assistant_id)
    system_message_json = {
        "role": "system",
        "content": assistant.instructions,
    }
    messages_json = [system_message_json]
    for message_obj in list(
        client.beta.threads.runs.steps.list(run_id=run_id, thread_id=thread_id).data
    )[:0:-1]:
        if message_obj.type == "message_creation":
            message_id = message_obj.step_details.message_creation.message_id
            message_content = (
                client.beta.threads.messages.retrieve(
                    message_id=message_id, thread_id=thread_id
                )
                .content[0]
                .text.value
            )
            messages_json.append(
                {
                    "role": "assistant",
                    "content": message_content,
                }
            )
            # TODO: handle annotations
        elif message_obj.type == "tool_calls":
            code_interpreter = message_obj.step_details.tool_calls[0].code_interpreter
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
    return messages_json


def run_until_complete(
    thread_id: str,
    run_id: str,
    assistant_id: str,
    model: str = "gpt-4-1106-preview",
    chat_logger: ChatLogger | None = None,
    sleep_time: int = 3,
    max_iterations: int = 1200,
):
    message_strings = []
    json_messages = []
    try:
        for i in range(max_iterations):
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            if run.status == "completed":
                logger.info(f"Run completed with {run.status}")
                break
            if run.status == "failed":
                logger.info(f"Run completed with {run.status}")
                raise Exception("Run failed")
            if run.status == "requires_action":
                tool_calls = [
                    tool_call
                    for tool_call in run.required_action.submit_tool_outputs.tool_calls
                    if tool_call.function.name == raise_error_schema["name"]
                ]
                if tool_calls:
                    arguments_parsed = json.loads(tool_calls[0].function.arguments)
                    raise AssistantRaisedException(arguments_parsed["message"])
            messages = client.beta.threads.messages.list(
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
                if i % 10 == 0:
                    logger.info(run.status)
            time.sleep(sleep_time)
    except (KeyboardInterrupt, SystemExit):
        client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run_id)
        logger.warning(f"Run cancelled: {run_id}")
        raise SystemExit
    for json_message in json_messages:
        logger.info(json_message["content"])
    return client.beta.threads.messages.list(
        thread_id=thread_id,
    )


def openai_assistant_call_helper(
    request: str,
    instructions: str | None = None,
    additional_messages: list[Message] = [],
    file_paths: list[str] = [], # use either file_paths or file_ids
    uploaded_file_ids: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = "gpt-4-1106-preview",
    sleep_time: int = 3,
    chat_logger: ChatLogger | None = None,
    assistant_id: str | None = None,
    assistant_name: str | None = None,
):
    file_ids = [] if not uploaded_file_ids else uploaded_file_ids
    file_object = None
    if not file_ids:
        for file_path in file_paths:
            if not any(file_path.endswith(extension) for extension in allowed_exts):
                os.rename(file_path, file_path + ".txt")
                file_path += ".txt"
            file_object = client.files.create(file=Path(file_path), purpose="assistants")
            file_ids.append(file_object.id)
    
    logger.debug(instructions)
    if assistant_id is None:
        assistant = client.beta.assistants.create(
            name=assistant_name,
            instructions=instructions,
            tools=tools,
            model=model,
        )
    else:
        assistant = client.beta.assistants.retrieve(assistant_id=assistant_id)
    thread = client.beta.threads.create()
    if file_ids:
        logger.info("Uploading files...")
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
    )
    run_until_complete(
        thread_id=thread.id,
        run_id=run.id,
        model=model,
        chat_logger=chat_logger,
        assistant_id=assistant.id,
        sleep_time=sleep_time,
    )
    if file_ids: client.files.delete(file_id=file_ids[0])
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
):
    retries = range(3)
    for _ in retries:
        try:
            (assistant_id, run_id, thread_id) = openai_assistant_call_helper(
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
            )
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
