import json
import traceback
from time import sleep
from typing import Callable

import openai
from loguru import logger
from openai import AzureOpenAI, OpenAI
from openai.pagination import SyncCursorPage
from openai.types.beta.threads.thread_message import ThreadMessage
from pydantic import BaseModel

from sweepai.config.server import (
    AZURE_API_KEY,
    DEFAULT_GPT4_32K_MODEL,
    IS_SELF_HOSTED,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
    OPENAI_API_VERSION,
)
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.openai_proxy import OpenAIProxy

if OPENAI_API_TYPE == "openai":
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=90) if OPENAI_API_KEY else None
elif OPENAI_API_TYPE == "azure":
    client = AzureOpenAI(
        azure_endpoint=OPENAI_API_BASE,
        api_key=AZURE_API_KEY,
        api_version=OPENAI_API_VERSION,
    )
    # DEFAULT_GPT4_32K_MODEL = AZURE_OPENAI_DEPLOYMENT  # noqa: F811

else:
    raise Exception("OpenAI API type not set, must be either 'openai' or 'azure'.")


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
        except Exception as e:
            logger.exception(f"Retry {attempt + 1} failed with error: {e}")
            error_message = str(e)
    raise Exception(
        f"Maximum retries reached. The call failed for call {error_message}"
    ) from e


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
    "elm",
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
    tools: list[dict[str, str]],
    model: str = DEFAULT_GPT4_32K_MODEL,
    chat_logger: ChatLogger | None = None,
    sleep_time: int = 3,
    max_iterations: int = 100,
    save_ticket_progress: save_ticket_progress_type | None = None,
    messages: list[Message] = [],
):
    # used for chat logger
    for i in range(max_iterations):
        # log our progress
        if i % 5 == 0:
            logger.info(
                f"run_until_complete iteration {i}, current message length: {len(messages)}"
            )
        # if we are somehow about to hit the max iterations, log a warning
        if i == max_iterations - 1:
            logger.warning(
                f"run_until_complete about to hit max iterations! iteration {i} out {max_iterations}"
            )
        # get the response from openai
        try:
            openai_proxy = OpenAIProxy()
            response = openai_proxy.call_openai(
                model,
                messages,
                tools,
                max_tokens=2048,
                temperature=0.2,
                # set max tokens later
            )
        # sometimes deployment for opennai is not found, retry after a minute
        except openai.NotFoundError as e:
            logger.error(
                f"Openai deployment not found on iteration {i} with error: {e}\n Retrying in 60 seconds..."
            )
            sleep(60)
            continue
        except Exception as e:
            logger.error(f"chat completions failed on interation {i} with error: {e}")
            sleep(sleep_time)
            continue

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        # extend conversation
        response_message_dict = response_message.dict()
        # in some cases the fields are None and we must replace these with empty strings
        for key, value in response_message_dict.items():
            if value is None:
                response_message_dict[key] = ""
        # if function_call is None we must remove it or else openai will throw an error
        if response_message_dict.get("function_call", "not in dict") == "":
            response_message_dict.pop("function_call")
        if response_message_dict.get("tool_calls", "not in dict") == "":
            response_message_dict.pop("tool_calls")

        messages.append(response_message_dict)
        # if a tool call was made
        if tool_calls:
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                tool_output = yield function_name, function_args
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_output,
                    }
                )  # extend conversation with function response
                if not tool_output:
                    break
        else:  # no tool call being made implies either an error or a success
            logger.info(
                f"no tool calls were made, we are done - message: {response_message}"
            )
            done_response = yield "done", {
                "status": "completed",
                "message": "Run completed successfully",
            }
            logger.info(
                f"run_until_complete done_response: {done_response} completed after {i} iterations"
            )
            if not done_response:
                break

        # on each iteration of the for loop, we will log to chat_logger
        if chat_logger is not None and len(messages):
            descriptive_messages = [message for message in messages]
            # for tool calls, the content is empty, replace that with the function contents
            for message in descriptive_messages:
                if message.get("content", "") == "" and "tool_calls" in message:
                    # if there were multiple tool calls, add them both
                    for tool_call in message["tool_calls"]:
                        message[
                            "content"
                        ] += f"\n\ntool_call: {tool_call.get('function', '')}"
            chat_logger.add_chat(
                {
                    "model": model,
                    "messages": descriptive_messages,
                    "output": descriptive_messages[-1]["content"],
                    "max_tokens": 1000,
                    "temperature": 0,
                }
            )
        # update ticket_progress
        # if save_ticket_progress is not None:
        #     save_ticket_progress(
        #         messages=messages
        #     )


def openai_assistant_call_helper(
    request: str,
    instructions: str | None = None,
    additional_messages: list[Message] = [],
    file_paths: list[str] = [],  # use either file_paths or file_ids
    uploaded_file_ids: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = DEFAULT_GPT4_32K_MODEL,
    sleep_time: int = 3,
    chat_logger: ChatLogger | None = None,
    assistant_id: str | None = None,
    assistant_name: str | None = None,
    save_ticket_progress: save_ticket_progress_type | None = None,
):
    logger.debug(instructions)
    messages = [{"role": "system", "content": instructions}]
    for message in additional_messages:
        messages.append({"role": message.role, "content": message.content})

    # tools must always be > 1
    if len(tools) > 1:
        return run_until_complete(
            tools=tools,
            messages=messages,
            model=model,
            chat_logger=chat_logger,
            sleep_time=sleep_time,
            save_ticket_progress=save_ticket_progress,
        )
    else:
        raise Exception("openai_assistant_call_helper tools must be > 1")


# Split in two so it can be cached
def openai_assistant_call(
    request: str,
    instructions: str | None = None,
    additional_messages: list[Message] = [],
    file_paths: list[str] = [],
    uploaded_file_ids: list[str] = [],
    tools: list[dict[str, str]] = [{"type": "code_interpreter"}],
    model: str = DEFAULT_GPT4_32K_MODEL,
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
        else DEFAULT_GPT4_32K_MODEL
    )
    posthog.capture(
        chat_logger.data.get("username") if chat_logger is not None else "anonymous",
        "call_assistant_api",
        {
            "query": request,
            "model": model,
            "username": (
                chat_logger.data.get("username", "anonymous")
                if chat_logger is not None
                else "anonymous"
            ),
            "is_self_hosted": IS_SELF_HOSTED,
            "trace": "".join(traceback.format_list(traceback.extract_stack())),
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
