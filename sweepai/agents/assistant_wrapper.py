import json
import re
import traceback
from time import sleep
from typing import Any, Callable, Optional

import openai
from loguru import logger
from openai.pagination import SyncCursorPage
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from pydantic import BaseModel

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, IS_SELF_HOSTED
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.openai_proxy import get_client
from sweepai.utils.anthropic_client import AnthropicClient

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

tool_call_parameters = {
    "analyze_problem_and_propose_plan": ["problem_analysis", "proposed_plan"],
    "search_codebase": ["justification", "file_name", "keyword"],
    "analyze_and_identify_changes": ["file_name", "changes"],
    "view_file": ["justification", "file_name"],
    "make_change": ["justification", "file_name", "original_code", "new_code"],
    "create_file": ["justification", "file_name", "file_path", "contents"],
    "submit_result": ["justification"],
}

def get_json_messages(
    thread_id: str,
    run_id: str,
    assistant_id: str,
):
    model, client = get_client()
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

# returns a dictionary of the tool call parameters, assumes correct
def parse_tool_call_parameters(tool_call_contents: str, parameters: list[str]) -> dict[str, Any]:
    tool_args = {}
    for param in parameters:
        param_regex = rf'<{param}>\s*(?P<{param}>.*?)\s*<\/{param}>'
        match = re.search(param_regex, tool_call_contents, re.DOTALL)
        if match:
            param_contents = match.group(param)
            tool_args[param] = param_contents
    return tool_args

# parse llm response for tool calls in xml format
def parse_tool_calls(response_contents: str) -> list[dict[str, Any]]:
    tool_calls = []
    # first get all tool calls
    tool_call_regex = r'<invoke>\s*(?P<function_call>.*?)\s*<\/invoke>'
    tool_call_matches = re.finditer(tool_call_regex, response_contents, re.DOTALL)

    # now we extract each tool name and its parameters
    for tool_call_match in tool_call_matches:
        tool_name_regex = r'<tool_name>\s*(?P<tool_name>.*?)\s*<\/tool_name>'
        tool_call_contents = tool_call_match.group("function_call")
        tool_name = re.search(tool_name_regex, tool_call_contents).group("tool_name").strip()
        # now we extract the arguments based on the tool name
        if tool_name in tool_call_parameters:
            # get parameters based off of tool name
            parameters = tool_call_parameters[tool_name]
            tool_call = { "tool": tool_name, 
                         "arguments": parse_tool_call_parameters(tool_call_contents, parameters) 
                        }
            tool_calls.append(tool_call)
        else:
            logger.debug(f"WARNING! Tool name {tool_name} not recognized")
    return tool_calls

def run_until_complete(
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
            client = AnthropicClient()                
            response = client.get_response_message(messages, max_tokens=3072, temperature=0.2, stop_sequences=["</invoke>"])
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
        # extend conversation
        response_role, response_contents = client.parse_role_content_from_response(response)
        if not response_contents:
            done_response = yield "done", {
                "status": "completed",
                "message": "Run completed",
            }, {"role": "assistant", "content": "Run completed"}
        # if a function call was made
        if "<invoke>" in response_contents:
            response_contents += "</invoke>\n</function_calls>"
        tool_calls = parse_tool_calls(response_contents)
        # extend conversation with llm, must rstrip to remove trailing whitespace or else anthropic complains
        messages.append({"role": response_role, "content": response_contents.rstrip() or  "No tool call made!"})
        # if a tool call was made
        done_response = None
        if len(tool_calls) > 1:
            logger.debug(f"WARNING MULTIPLE TOOL CALLS MADE: {len(tool_calls)}")
        if tool_calls:
            for tool_call in tool_calls:
                tool_name = tool_call['tool']
                try:
                    tool_args = tool_call["arguments"]
                except json.JSONDecodeError as e:
                    logger.debug(
                        f'Error: could not decode function arguments: {tool_call["arguments"]}'
                    )
                    tool_output = f"ERROR\nCould not decode function arguments:\n{e}"
                else:
                    if tool_name == "submit_result":
                        logger.info(
                            "Submit function was called"
                        )
                        if "justification" in tool_args:
                            done_response = yield "done", {
                                "status": "completed",
                                "message": tool_args["justification"],
                            }, {"role": response_role, "content": response_contents}
                        else:
                            done_response = yield "done", {
                                "status": "completed",
                                "message": "No justification provided",
                            }, {"role": response_role, "content": response_contents}
                        logger.info(
                            f"run_until_complete done_response: {done_response} completed after {i} iterations"
                        )
                        if not done_response:
                            break
                    else:
                        logger.debug(
                            f"tool_call: {tool_name} with args: {tool_args}"
                        )
                        tool_output: str = yield tool_name, tool_args, {"role": response_role, "content": response_contents}
                        if not tool_output:
                            break
                        messages.append(
                            {
                                "role": "user",
                                "content": f"{tool_output.rstrip()}",
                            }
                        )  # extend conversation with function response
                
        else:  # no tool call being made implies either an error or a success
            logger.error(
                f"No tool calls were made, yielding with tool_call no_tool_call: {response_contents}"
            )
            done_response = yield "no_tool_call", {
                "status": "no tool call",
                "message": "No tool call made",
            }, {"role": response_role, "content": response_contents}
            messages.append(
                {
                    "role": "user",
                    "content": f"{done_response.rstrip()}",
                }
            )  # extend conversation with function response
            normal_messages_remaining -= 1
            if normal_messages_remaining < 0:
                return

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
    return messages


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
    return run_until_complete(
        tools=tools,
        messages=messages,
        model=model,
        chat_logger=chat_logger,
        sleep_time=sleep_time,
        save_ticket_progress=save_ticket_progress,
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
    model, client = get_client()
    if chat_logger and chat_logger.use_faster_model():
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
            return response
        except AssistantRaisedException as e:
            logger.warning(e.message)
        except Exception as e:
            logger.error(e)
            raise e