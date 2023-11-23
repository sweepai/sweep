import time
from pathlib import Path

from loguru import logger
from openai import OpenAI

from sweepai.config.server import OPENAI_API_KEY
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger

client = OpenAI(api_key=OPENAI_API_KEY)


@file_cache(ignore_params=["chat_logger"])
def openai_assistant_call(
    name: str,
    instructions: str,
    file_paths: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = "gpt-4-1106-preview",
    sleep_time: int = 3,
    chat_logger: ChatLogger | None = None,
):
    file_ids = []
    for file_path in file_paths:
        file_object = client.files.create(file=Path(file_path), purpose="assistants")
        file_ids.append(file_object.id)

    assistant = client.beta.assistants.create(
        name=name,
        instructions=instructions,
        tools=tools,
        model=model,
        file_ids=file_ids,
    )
    thread = client.beta.threads.create()
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )
    message_strings = []
    for _ in range(1200):
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run.status == "completed":
            break
        messages = client.beta.threads.messages.list(
            thread_id=thread.id,
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
                        "messages": message_strings[1:],
                        "output": message_strings[0],
                        "max_tokens": 1000,
                        "temperature": 0,
                    }
                )
        else:
            logger.info(run.status)
        time.sleep(sleep_time)
    messages = client.beta.threads.messages.list(
        thread_id=thread.id,
    )
    return messages
