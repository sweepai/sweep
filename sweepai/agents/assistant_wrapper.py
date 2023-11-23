import time
from pathlib import Path

from loguru import logger
from openai import OpenAI

from sweepai.config.server import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)


def openai_assistant_call(
    name: str,
    instructions: str,
    file_paths: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = "gpt-4-1106-preview",
    sleep_time: int = 3,
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
    messages = []
    for _ in range(1200):
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run.status == "completed":
            break
        logger.info(run.status)
        messages = client.beta.threads.messages.list(
            thread_id=thread.id,
        )
        current_messages = [message.content[0].text.value for message in messages.data]
        if messages != current_messages and current_messages:
            logger.info(current_messages[0])
            messages = current_messages
        time.sleep(sleep_time)
    messages = client.beta.threads.messages.list(
        thread_id=thread.id,
    )
    return messages
