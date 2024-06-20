import copy
import os


from loguru import logger
from sweepai.agents.modify_utils import (NO_TOOL_CALL_PROMPT, SLOW_MODEL, create_user_message, get_error_message_dict, get_replaces_per_fcr, render_current_task, render_plan, instructions, modify_tools, SUBMIT_TASK_MOCK_FUNCTION_CALL, linter_warning_prompt, compile_fcr, validate_and_parse_function_call, handle_function_call, tasks_completed, changes_made, get_current_task_index, MODEL)
from sweepai.core.chat import ChatGPT, continuous_llm_calls
from sweepai.core.entities import FileChangeRequest, Message, parse_fcr
from sweepai.dataclasses.code_suggestions import StatefulCodeSuggestion
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.code_validators import format_file
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.streamable_functions import streamable

def generate_code_suggestions(
    modify_files_dict: dict[str, dict[str, str]],
    fcrs: list[FileChangeRequest],
    error_messages_dict: dict[int, str],
    cloned_repo: ClonedRepo,
) -> list[StatefulCodeSuggestion]:
    modify_order = []
    for fcr in fcrs:
        if fcr.filename not in modify_order:
            modify_order.append(fcr.filename)

    code_suggestions = []
    for file_path in modify_order:
        if file_path in modify_files_dict:
            file_data = modify_files_dict[file_path]
            if file_data["original_contents"] != file_data["contents"]:
                code_suggestions.append(StatefulCodeSuggestion(
                    file_path=file_path,
                    original_code=file_data["original_contents"],
                    new_code=file_data["contents"],
                    file_contents=file_data["original_contents"],
                    state="done"
                ))
    
    current_fcr_index = next((i for i, fcr in enumerate(fcrs) if not fcr.is_completed), -1)
    if current_fcr_index >= 0:
        for i, fcr in enumerate(fcrs):
            if i < current_fcr_index:
                continue
            else:
                parsed_fcr = parse_fcr(fcr)
                try:
                    file_contents = cloned_repo.get_file_contents(fcr.filename)
                except FileNotFoundError:
                    file_contents = ""
                code_suggestions.append(StatefulCodeSuggestion(
                    file_path=fcr.filename,
                    original_code=parsed_fcr["original_code"][0] if parsed_fcr["original_code"] else "",
                    new_code=parsed_fcr["new_code"][0] if parsed_fcr["new_code"] else "",
                    file_contents=file_contents,
                    state=("processing" if i == current_fcr_index else "pending"),
                    error=error_messages_dict.get(i, None)
                ))
    return code_suggestions

@streamable
def modify(
    fcrs: list[FileChangeRequest],
    request: str,
    cloned_repo: ClonedRepo,
    relevant_filepaths: list[str],
    chat_logger: ChatLogger | None = None,
    use_openai: bool = False,
    previous_modify_files_dict: dict[str, dict[str, str]] = {},
    renames_dict: dict[str, str] = {},
    raise_on_max_iterations: bool = False,
) -> dict[str, dict[str, str]]:
    # join fcr in case of duplicates
    use_openai = False
    # handles renames in cloned_repo
    # TODO: handle deletions here - it can cause crashes
    for file_path, new_file_path in renames_dict.items():
        file_contents = cloned_repo.get_file_contents(file_path)
        with open(os.path.join(cloned_repo.repo_dir, new_file_path), "w") as f:
            f.write(file_contents)
        os.remove(os.path.join(cloned_repo.repo_dir, file_path))
    
    # handle renames first
    if not fcrs:
        return previous_modify_files_dict

    user_message = create_user_message(
        fcrs=fcrs,
        request=request,
        cloned_repo=cloned_repo,
        relevant_filepaths=relevant_filepaths,
    )
    chat_gpt = ChatGPT()
    llm_state = {
        "initial_check_results": {},
        "done_counter": 0, # keep track of how many times the submit_task tool has been called
        "request": request,
        "plan": render_plan(fcrs), 
        "current_task": render_current_task(fcrs),
        "user_message_index": 1,  # used for detailed chat logger messages
        "user_message_index_chat_logger": 1,  # used for detailed chat logger messages
        "fcrs": fcrs,
        "previous_attempt": "",
        "changes_per_fcr": [get_replaces_per_fcr(fcr) for fcr in fcrs], # how many old/new code pairs there are per fcr
        "completed_changes_per_fcr": [0 for _ in fcrs], # how many successful changes have been applied per fcr
        "attempt_lazy_change": True, # whether or not we attempt to bypass the llm call and apply old/new code pair directly
        "attempt_count": 0, # how many times we have attempted to apply the old/new code pair
        "visited_set": set(), # keep track of which outputs have been attempted
        "status_messages": [],
    }
    full_instructions = instructions + modify_tools
    chat_gpt.messages = [Message(role="system", content=full_instructions)]
    try:
        if compiled_fcr := compile_fcr(fcrs[0], 0):
            chat_gpt.messages.append(Message(role="user", content=f"Here is the initial user request, plan, and state of the code files:\n{user_message}"))
            function_calls_string = compiled_fcr
            chat_gpt.messages.append(Message( # this will happen no matter what
                role="assistant",
                content=function_calls_string
            ))
            # update messages to make it seem as if it called the fcr
            # update state if it's bad
            # TODO: handling logic to be moved out
            function_call: AnthropicFunctionCall = validate_and_parse_function_call(function_calls_string, chat_gpt) # this will raise if it's bad but compile_fcr should guarantee it's good
        else:
            model = MODEL
            logger.info(f"Using model: {model}")
            function_calls_string = continuous_llm_calls(
                chat_gpt,
                content=f"Here is the initial user request, plan, and state of the code files:\n{user_message}",
                model=model,
                message_key="user_request",
                stop_sequences=["</function_call>"],
                use_openai=use_openai,
            )
    except Exception as e:
        logger.error(f"Error in chat_anthropic: {e}")
        if chat_logger:
            chat_logger.add_chat(
                {
                    "model": chat_gpt.model,
                    "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                    "output": f"ERROR:\n{e}\nEND OF ERROR",
                })
        return {}
    if not previous_modify_files_dict:
        previous_modify_files_dict = {}
    modify_files_dict = copy.deepcopy(previous_modify_files_dict)

    # this message list is for the chat logger to have a detailed insight into why failures occur
    detailed_chat_logger_messages = [{"role": message.role, "content": message.content} for message in chat_gpt.messages]
    # used to determine if changes were made
    error_messages_dict = get_error_message_dict(fcrs, cloned_repo, modify_files_dict, renames_dict)
    previous_modify_files_dict = copy.deepcopy(modify_files_dict)
    for i in range(len(fcrs) * 15):
        yield generate_code_suggestions(modify_files_dict, fcrs, error_messages_dict, cloned_repo)
        function_call = validate_and_parse_function_call(function_calls_string, chat_gpt)
        if function_call:
            num_of_tasks_done = tasks_completed(fcrs)
            # note that detailed_chat_logger_messages is meant to be modified in place by handle_function_call
            function_output, modify_files_dict, llm_state = handle_function_call(
                cloned_repo,
                function_call,
                modify_files_dict,
                llm_state,
                chat_logger_messages=detailed_chat_logger_messages,
                use_openai=use_openai,
            )
            print(function_output)
            fcrs = llm_state["fcrs"]
            if function_output == "DONE":
                # add the diff of all changes to chat_logger
                if chat_logger:
                    final_message = "DONE\nHere is a summary of all the files changed:\n\n"
                    reverse_renames_dict = {v: k for k, v in renames_dict.items()}
                    for file_name, file_data in modify_files_dict.items():
                        tofile = file_name
                        fromfile = reverse_renames_dict.get(tofile, tofile)
                        # handle renames
                        if file_diff := generate_diff(
                            file_data['original_contents'],
                            file_data['contents'],
                            fromfile=fromfile,
                            tofile=tofile
                        ):
                            final_message += f"\nChanges made to {file_name}:\n{file_diff}"
                    chat_logger.add_chat({
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": f"{final_message}",
                    })
                break
            # breakpoint()
            detailed_chat_logger_messages.append({"role": "user", "content": function_output})

            if modify_files_dict: # update the state of the LLM
                user_message = create_user_message(
                    fcrs=fcrs,
                    request=request,
                    cloned_repo=cloned_repo,
                    relevant_filepaths=relevant_filepaths,
                    modify_files_dict=modify_files_dict
                )
                user_message = f"Here is the UPDATED user request, plan, and state of the code changes. REVIEW THIS CAREFULLY!\n{user_message}"
                # state cleanup should only occur after a task has been finished and if a change was made and if a change was made
                current_num_of_tasks_done = tasks_completed(fcrs)
                if changes_made(modify_files_dict, previous_modify_files_dict) and current_num_of_tasks_done > num_of_tasks_done:
                    # remove the previous user message and add it to the end, do not remove if it is the inital user message
                    chat_gpt.messages = chat_gpt.messages[:1]
                    detailed_chat_logger_messages = detailed_chat_logger_messages[:1]
                    chat_gpt.messages.append(Message(role="user", content=user_message))
                    detailed_chat_logger_messages.append({"role": "user", "content": user_message})
                    # update the index
                    llm_state["user_message_index"] = len(chat_gpt.messages) - 1
                    llm_state["user_message_index_chat_logger"] = len(detailed_chat_logger_messages) - 1
                previous_modify_files_dict = copy.deepcopy(modify_files_dict)
        else:
            function_output = NO_TOOL_CALL_PROMPT
        if chat_logger:
            if i == len(fcrs) * 10 - 1:
                chat_logger.add_chat(
                    {
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": f"WARNING We have reached the end the max amount of iterations: {i + 1}, but we have not finished with our changes yet!",
                    })
            else:
                chat_logger.add_chat(
                    {
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": detailed_chat_logger_messages[-1]["content"],
                    })
        try:
            function_calls_string = ""
            compiled_fcr = ""
            current_fcr_index = get_current_task_index(fcrs)
            change_in_fcr_index = llm_state["completed_changes_per_fcr"][current_fcr_index]
            max_changes = llm_state["changes_per_fcr"][current_fcr_index]
            if change_in_fcr_index >= max_changes:
                function_calls_string = SUBMIT_TASK_MOCK_FUNCTION_CALL.format(justification=f"Task {current_fcr_index} is now complete.")
            else:
                # on first attempt of a new task we use the first fcr
                if llm_state["attempt_lazy_change"]:
                    if compiled_fcr := compile_fcr(fcrs[current_fcr_index], change_in_fcr_index):
                        function_calls_string = compiled_fcr
                        function_call = validate_and_parse_function_call(function_calls_string, chat_gpt) # this will raise if it's bad but compile_fcr should guarantee it's good
                        logger.info(f"Function call:\n{function_call}")
                        # update messages to make it seem as if it called the fcr
                        chat_gpt.messages.append(Message(
                            role="assistant",
                            content=function_calls_string
                        ))
                # if previous things go wrong we make llm call
                if not function_calls_string:
                    if linter_warning_prompt in function_output:
                        llm_state["attempt_count"] = 3 # skip to opus if there is a linter warning
                    model = MODEL if llm_state["attempt_count"] < 3 else SLOW_MODEL
                    # logger.info(f"Using model: {model}")
                    function_calls_string = continuous_llm_calls(
                        chat_gpt,
                        content=function_output,
                        model=model,
                        stop_sequences=["</function_call>"],
                        use_openai=use_openai if llm_state["attempt_count"] < 3 else False,
                    )
                    if function_calls_string in llm_state["visited_set"]:
                        if llm_state["attempt_count"] < 3:
                            logger.warning(f"Function call {function_calls_string} has already been visited, retrying with a different model.")
                            llm_state["attempt_count"] = 3
                            function_calls_string = continuous_llm_calls(
                                chat_gpt,
                                content=function_output,
                                model=model,
                                stop_sequences=["</function_call>"],
                                use_openai=use_openai,
                            )
                            if function_calls_string in llm_state["visited_set"]:
                                logger.warning(f"Function call {function_calls_string} has already been visited, skipping task {current_fcr_index}.")
                                function_calls_string = SUBMIT_TASK_MOCK_FUNCTION_CALL.format(justification=f"Skipping task {current_fcr_index} due to too many retries.")
                            else:
                                llm_state["visited_set"] = set()
                        else:
                            logger.warning(f"Function call {function_calls_string} has already been visited, skipping task {current_fcr_index}.")
                            function_calls_string = SUBMIT_TASK_MOCK_FUNCTION_CALL.format(justification=f"Skipping task {current_fcr_index} due to too many retries.")
            detailed_chat_logger_messages.append({"role": "assistant", "content": function_calls_string})
        except Exception as e:
            logger.error(f"Error in chat_anthropic: {e}")
            with open("msg.txt", "w") as f:
                for message in chat_gpt.messages:
                    f.write(f"{message.content}\n\n")
            if chat_logger is not None:
                chat_logger.add_chat(
                    {
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": f"ERROR: AN ERROR OCCURED ON ITERATION {i + 1}:\n{e}\nEND OF ERROR",
                    })
            break
    else:
        logger.error("Max iterations reached")
        if raise_on_max_iterations:
            raise Exception("Max iterations reached")

    for file_path, file_data in modify_files_dict.items():
        formatted_contents = format_file(
            file_path, file_data["contents"], cloned_repo.repo_dir
        )
        # formatted_contents can invalidate changes when prettier/formatter is out of sync
        # only accept the changes if the formatted contents would not reveert all changes
        if file_data["original_contents"] != formatted_contents:
            file_data["contents"] = formatted_contents

    diff_string = ""
    for file_name, file_data in modify_files_dict.items():
        if diff := generate_diff(
            file_data['original_contents'], file_data['contents']
        ):
            diff_string += f"\nChanges made to {file_name}:\n{diff}"
    logger.info("\n".join(generate_diff(file_data["original_contents"], file_data["contents"]) for file_data in modify_files_dict.values())) # adding this as a useful way to render the diffs
    yield generate_code_suggestions(modify_files_dict, fcrs, error_messages_dict, cloned_repo)
    return modify_files_dict


if __name__ == "__main__":
    pass
