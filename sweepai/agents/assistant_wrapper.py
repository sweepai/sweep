import json
import os
import re
import time
import traceback
from time import sleep
from typing import Callable, Optional

import openai
from anyio import Path
from loguru import logger
from openai import AzureOpenAI, OpenAI
from openai.pagination import SyncCursorPage
from openai.types.beta.threads.thread_message import ThreadMessage
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from pydantic import BaseModel

from sweepai.agents.assistant_functions import raise_error_schema, submit_schema
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
    thread_id: str,
    run_id: str,
    assistant_id: str,
    model: str = DEFAULT_GPT4_32K_MODEL,
    chat_logger: ChatLogger | None = None,
    sleep_time: int = 3,
    max_iterations: int = 2000,
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
                logger.info(
                    f"Run completed with {run.status} (i={num_tool_calls_made})"
                )
                done_response = yield "done", {
                    "status": "completed",
                    "message": "Run completed successfully",
                }
                if not done_response:
                    break
                else:
                    run = client.beta.threads.runs.create(
                        thread_id=thread_id,
                        assistant_id=assistant_id,
                        instructions=done_response,
                        model=model,
                    )
            elif run.status in ("cancelled", "cancelling", "failed", "expired"):
                logger.info(
                    f"Run completed with {run.status} (i={num_tool_calls_made}) and reason {run.last_error}."
                )
                done_response = yield "done", {
                    "status": run.status,
                    "message": "Run failed",
                }
                if not done_response:
                    raise Exception(
                        f"Run failed assistant_id={assistant_id}, run_id={run_id}, thread_id={thread_id} with status {run.status} (i={num_tool_calls_made})"
                    )
                else:
                    run = client.beta.threads.runs.create(
                        thread_id=thread_id,
                        assistant_id=assistant_id,
                        instructions=done_response,
                        model=model,
                    )
            elif run.status == "requires_action":
                num_tool_calls_made += 1
                if num_tool_calls_made > 15 and model.startswith("gpt-3.5"):
                    raise AssistantRaisedException(
                        "Too many tool calls made on GPT 3.5."
                    )
                raw_tool_calls = [
                    tool_call
                    for tool_call in run.required_action.submit_tool_outputs.tool_calls
                ]
                tool_outputs = []
                tool_calls = []
                if any(
                    [
                        tool_call.function.name == raise_error_schema["name"]
                        for tool_call in raw_tool_calls
                    ]
                ):
                    arguments_parsed = json.loads(tool_calls[0].function.arguments)
                    raise AssistantRaisedException(arguments_parsed["message"])
                # tool_calls = raw_tool_calls
                for tool_call in raw_tool_calls:
                    try:
                        tool_call_arguments = re.sub(
                            r"\\+'", "", tool_call.function.arguments
                        )
                        function_input: dict = json.loads(tool_call_arguments)
                    except Exception:
                        logger.warning(
                            f"Could not parse function arguments (i={num_tool_calls_made}): {tool_call_arguments}"
                        )
                        tool_outputs.append(
                            {
                                "tool_call_id": tool_call.id,
                                "output": "FAILURE: Could not parse function arguments.",
                            }
                        )
                        continue
                    tool_function_name = tool_call.function.name
                    tool_function_input = function_input
                    # OpenAI has a bug where it calls the imaginary function "multi_tool_use.parallel"
                    # Based on https://github.com/phdowling/openai_multi_tool_use_parallel_patch/blob/main/openai_multi_tool_use_parallel_patch.py
                    if tool_function_name in ("multi_tool_use.parallel", "parallel"):
                        for fake_i, fake_tool_use in function_input["tool_uses"]:
                            function_input = fake_tool_use["parameters"]
                            function_name: str = fake_tool_use["recipient_name"]
                            function_name = function_name.removeprefix("functions.")
                            tool_calls.append(
                                (
                                    f"{tool_call.id}_{fake_i}",
                                    function_name,
                                    function_input,
                                )
                            )
                    else:
                        tool_calls.append(
                            (tool_call.id, tool_function_name, tool_function_input)
                        )

                for tool_call_id, tool_function_name, tool_function_input in tool_calls:
                    tool_output = yield tool_function_name, tool_function_input
                    tool_output_formatted = {
                        "tool_call_id": tool_call_id,
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
                message.content[0].text.value if message.content else ""
                for message in messages.data
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
            if i == max_iterations - 1:
                logger.warning(
                    f"run_until_complete hit max iterations, run.status is {run.status}"
                )
            time.sleep(sleep_time)
    except (KeyboardInterrupt, SystemExit):
        client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run_id)
        logger.warning(f"Run cancelled: {run_id} (n={num_tool_calls_made})")
        raise SystemExit
    if save_ticket_progress is not None:
        save_ticket_progress(
            assistant_id=assistant_id,
            thread_id=thread_id,
            run_id=run_id,
        )
    for json_message in json_messages:
        logger.info(f'(n={num_tool_calls_made}) {json_message["content"]}')
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
    model: str = DEFAULT_GPT4_32K_MODEL,
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


def run_until_complete_unstable(
    tools: list[dict[str, str]],
    model: str = DEFAULT_GPT4_32K_MODEL,
    chat_logger: ChatLogger | None = None,
    sleep_time: int = 3,
    max_iterations: int = 100,
    save_ticket_progress: save_ticket_progress_type | None = None,
    messages: list[Message] = [],
):
    normal_messages_remaining = 3
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
        tool_calls = fix_tool_calls(response_message.tool_calls)
        response_message.tool_calls = tool_calls
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
        done_response = None
        if tool_calls:
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                # if function_name == submit_schema["name"]:
                #     logger.info(
                #         f"Submit function was called"
                #     )
                #     try:
                #         function_args = json.loads(tool_call.function.arguments)
                #     except json.JSONDecodeError as e:
                #         logger.debug(
                #             f"Error: could not decode function arguments: {tool_call.function.args}"
                #         )
                #         tool_output = f"ERROR\nCould not decode function arguments:\n{e}"
                #     else:
                #         done_response = yield "done", {
                #             "status": "completed",
                #             "message": function_args["justification"],
                #         }
                #         logger.info(
                #             f"run_until_complete done_response: {done_response} completed after {i} iterations"
                #         )
                #     if not done_response:
                #         break
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    logger.debug(
                        f"Error: could not decode function arguments: {tool_call.function.args}"
                    )
                    tool_output = f"ERROR\nCould not decode function arguments:\n{e}"
                else:
                    if function_name == submit_schema["name"]:
                        logger.info(
                            f"Submit function was called"
                        )
                        done_response = yield "done", {
                            "status": "completed",
                            "message": function_args["justification"],
                        }
                        logger.info(
                            f"run_until_complete done_response: {done_response} completed after {i} iterations"
                        )
                        if not done_response:
                            break
                    else:
                        logger.debug(
                            f"tool_call: {function_name} with args: {function_args}"
                        )
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
            # logger.info(
            #     f"no tool calls were made, we are done - message: {response_message}"
            # )
            logger.error(
                f"No tool calls were made, use the submit function instead."
            )
            # done_response = yield "done", {
            #     "status": "completed",
            #     "message": "Run completed successfully",
            # }
            done_response = "Please use the submit function to indicate that you have completed the task."
            normal_messages_remaining -= 1
            if normal_messages_remaining < 0:
                raise Exception(
                    "No tool calls were made, use the submit function instead."
                )

            # logger.info(
            #     f"run_until_complete done_response: {done_response} completed after {i} iterations"
            # )
            # if not done_response:
            #     break

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


def openai_assistant_call_helper_unstable(
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
        return run_until_complete_unstable(
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
def openai_assistant_call_unstable(
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
    if chat_logger.use_faster_model():
        raise Exception("GPT-3.5 is not supported on assistant calls.")
    model = DEFAULT_GPT4_32K_MODEL
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
            response = openai_assistant_call_helper_unstable(
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

openai_assistant_call = openai_assistant_call_unstable
