import time
from pathlib import Path

from loguru import logger
from openai import OpenAI
from openai.pagination import SyncCursorPage
from openai.types.beta.threads.thread_message import ThreadMessage
from pydantic import BaseModel

from sweepai.config.server import OPENAI_API_KEY
from sweepai.core.entities import Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger

client = OpenAI(api_key=OPENAI_API_KEY)


class AssistantResponse(BaseModel):
    messages: SyncCursorPage[ThreadMessage]
    assistant_id: str
    run_id: str
    thread_id: str


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
    )[::-1]:
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
            messages_json.append(
                {
                    "role": "assistant",
                    "content": f"Code interpreter input:\n```\n{input_}\n```",
                }
            )
            outputs = code_interpreter.outputs
            output = outputs[0].logs if outputs else "__No output__"
            messages_json.append(
                {
                    "role": "user",
                    "content": f"Code interpreter output:\n```\n{output}\n```",
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
    try:
        for i in range(max_iterations):
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            if run.status == "completed":
                break
            if run.status == "failed":
                raise Exception("Run failed")
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
                if chat_logger is not None:
                    chat_logger.add_chat(
                        {
                            "model": model,
                            "messages": get_json_messages(
                                thread_id=thread_id,
                                run_id=run_id,
                                assistant_id=assistant_id,
                            ),
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
    return client.beta.threads.messages.list(
        thread_id=thread_id,
    )


@file_cache(ignore_params=["chat_logger"])
def openai_assistant_call(
    name: str,
    instructions: str,
    additional_messages: list[Message] = [],
    file_paths: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = "gpt-4-1106-preview",
    sleep_time: int = 3,
    chat_logger: ChatLogger | None = None,
    assistant_id: str | None = None,
):
    file_ids = []
    for file_path in file_paths:
        file_object = client.files.create(file=Path(file_path), purpose="assistants")
        file_ids.append(file_object.id)

    logger.debug(instructions)
    if assistant_id is None:
        assistant = client.beta.assistants.create(
            name=name,
            instructions=instructions,
            tools=tools,
            model=model,
        )
    else:
        assistant = client.beta.assistants.retrieve(assistant_id=assistant_id)
    thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=instructions,
        file_ids=file_ids,
    )
    for message in additional_messages:
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message.content,
        )
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )
    messages = run_until_complete(
        thread_id=thread.id,
        run_id=run.id,
        model=model,
        chat_logger=chat_logger,
        assistant_id=assistant.id,
        sleep_time=sleep_time,
    )
    return AssistantResponse(
        messages=messages,
        assistant_id=assistant.id,
        run_id=run.id,
        thread_id=thread.id,
    )
