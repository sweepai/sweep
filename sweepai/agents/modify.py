import copy


from loguru import logger
from sweepai.agents.modify_utils import (create_user_message, get_replaces_per_fcr, render_current_task, render_plan, instructions, modify_tools, modify_tools_openai, SUBMIT_TASK_MOCK_FUNCTION_CALL, linter_warning_prompt, compile_fcr, validate_and_parse_function_call, validate_and_parse_function_call_openai, handle_function_call, tasks_completed, changes_made, get_current_task_index, MODEL, SLOW_MODEL)
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import ClonedRepo


def modify(
    fcrs: list[FileChangeRequest],
    request: str,
    cloned_repo: ClonedRepo,
    relevant_filepaths: list[str],
    chat_logger: ChatLogger | None = None,
    use_openai: bool = False,
    previous_modify_files_dict: dict[str, dict[str, str]] = {},
) -> dict[str, dict[str, str]]:
    # join fcr in case of duplicates
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
    }
    full_instructions = instructions + (modify_tools_openai if use_openai else modify_tools)
    chat_gpt.messages = [Message(role="system", content=full_instructions)]
    try:
        if fcrs[0].change_type == "modify" and (compiled_fcr := compile_fcr(fcrs[0], 0)):
            chat_gpt.messages.append(Message(role="user", content=f"Here is the intial user request, plan, and state of the code files:\n{user_message}"))
            function_calls_string = compiled_fcr
            chat_gpt.messages.append(Message( # this will happen no matter what
                role="assistant",
                content=function_calls_string
            ))
            # update messages to make it seem as if it called the fcr
            # update state if it's bad
            # TODO: handling logic to be moved out
            function_call = validate_and_parse_function_call(function_calls_string, chat_gpt) # this will raise if it's bad but compile_fcr should guarantee it's good
            if function_call.function_parameters["original_code"] == function_call.function_parameters["new_code"]:
                current_fcr_index = get_current_task_index(llm_state["fcrs"])
                llm_state["completed_changes_per_fcr"][current_fcr_index] += 1
                for fcr in llm_state["fcrs"]:
                    if not fcr.is_completed:
                        fcr.is_completed = True # incrementing because we should skip bad calls
                        break
                llm_state["attempt_count"] = 0
                llm_state['current_task'] = render_current_task(llm_state["fcrs"]) # rerender the current task
                user_response = f"SUCCESS\n\nThe previous task is now complete. Please move on to the next task. {llm_state['current_task']}"
                llm_state["attempt_lazy_change"] = True
                llm_state["visited_set"] = set()
                function_calls_string = chat_gpt.chat_anthropic(
                    content=user_response,
                    stop_sequences=["</function_call>"],
                    model=MODEL,
                    message_key="user_request",
                    use_openai=use_openai,
                )
        else:
            model = MODEL
            logger.info(f"Using model: {model}")
            function_calls_string = chat_gpt.chat_anthropic(
                content=f"Here is the intial user request, plan, and state of the code files:\n{user_message}",
                stop_sequences=["</function_call>"],
                model=model,
                message_key="user_request",
                use_openai=use_openai,
            )
    except Exception as e:
        logger.error(f"Error in chat_anthropic: {e}")
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
    previous_modify_files_dict = copy.deepcopy(modify_files_dict)
    for i in range(len(fcrs) * 15):
        if use_openai:
            function_call = validate_and_parse_function_call_openai(function_calls_string, chat_gpt)
        else:
            function_call = validate_and_parse_function_call(function_calls_string, chat_gpt)
        if function_call:
            num_of_tasks_done = tasks_completed(fcrs)
            # note that detailed_chat_logger_messages is meant to be modified in place by handle_function_call
            function_output, modify_files_dict, llm_state = handle_function_call(cloned_repo, function_call, modify_files_dict, llm_state, chat_logger_messages=detailed_chat_logger_messages, use_openai=use_openai)
            fcrs = llm_state["fcrs"]
            if function_output == "DONE":
                # add the diff of all changes to chat_logger
                if chat_logger:
                    final_message = "DONE\nHere is a summary of all the files changed:\n\n"
                    for file_name, file_data in modify_files_dict.items():
                        if file_diff := generate_diff(
                            file_data['original_contents'],
                            file_data['contents'],
                        ):
                            final_message += f"\nChanges made to {file_name}:\n{file_diff}"
                    chat_logger.add_chat({
                        "model": chat_gpt.model,
                        "messages": detailed_chat_logger_messages,
                        "output": f"{final_message}",
                    })
                break
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
            function_output = "FAILURE: No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n" \
                + "<function_call>\n<invoke>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</invoke>\n</function_call>"
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
                    if fcrs[current_fcr_index].change_type == "modify" and (compiled_fcr := compile_fcr(fcrs[current_fcr_index], change_in_fcr_index)):
                        function_calls_string = compiled_fcr
                        function_call = validate_and_parse_function_call(function_calls_string, chat_gpt) # this will raise if it's bad but compile_fcr should guarantee it's good
                        if function_call.function_parameters["original_code"] == function_call.function_parameters["new_code"]:
                            current_fcr_index = get_current_task_index(llm_state["fcrs"])
                            llm_state["completed_changes_per_fcr"][current_fcr_index] += 1
                            for fcr in llm_state["fcrs"]:
                                if not fcr.is_completed:
                                    fcr.is_completed = True # incrementing because we should skip bad calls
                                    break
                            if all(
                                fcr.is_completed for fcr in llm_state["fcrs"]
                            ):
                                return modify_files_dict
                            llm_state["attempt_count"] = 0
                            llm_state['current_task'] = render_current_task(llm_state["fcrs"]) # rerender the current task
                            llm_state["attempt_lazy_change"] = True
                            llm_state["visited_set"] = set()
                            user_response = f"SUCCESS\n\nThe previous task is now complete. Please move on to the next task. {llm_state['current_task']}"
                            function_calls_string = chat_gpt.chat_anthropic(
                                content=user_response,
                                stop_sequences=["</function_call>"],
                                model=MODEL,
                                message_key="user_request",
                                use_openai=use_openai,
                            )
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
                    logger.info(f"Using model: {model}")
                    function_calls_string = chat_gpt.chat_anthropic(
                        content=function_output,
                        model=model,
                        stop_sequences=["</function_call>"],
                        use_openai=use_openai,
                    )
                    if function_calls_string in llm_state["visited_set"]:
                        if llm_state["attempt_count"] < 3:
                            logger.warning(f"Function call {function_calls_string} has already been visited, retrying with a different model.")
                            llm_state["attempt_count"] = 3
                            function_calls_string = chat_gpt.chat_anthropic(
                                content=SLOW_MODEL,
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
    diff_string = ""
    for file_name, file_data in modify_files_dict.items():
        if diff := generate_diff(
            file_data['original_contents'], file_data['contents']
        ):
            diff_string += f"\nChanges made to {file_name}:\n{diff}"
    logger.info("\n".join(generate_diff(file_data["original_contents"], file_data["contents"]) for file_data in modify_files_dict.values())) # adding this as a useful way to render the diffs
    return modify_files_dict


if __name__ == "__main__":
    pass