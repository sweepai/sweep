import os
import json
import subprocess
import traceback
from collections import defaultdict

from loguru import logger

from sweepai.agents.assistant_wrapper import openai_assistant_call, tool_call_parameters
from sweepai.agents.agent_utils import ensure_additional_messages_length
from sweepai.config.client import SweepConfig
from sweepai.core.entities import AssistantRaisedException, FileChangeRequest, Message
from sweepai.core.reflection_utils import ModifyEvaluatorAgent
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.diff import generate_diff
from sweepai.utils.file_utils import read_file_with_fallback_encodings
from sweepai.utils.github_utils import ClonedRepo, update_file
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.str_utils import get_all_indices_of_substring
from sweepai.utils.utils import CheckResults, get_check_results
from sweepai.utils.modify_utils import post_process_rg_output, manual_code_check

# Pre-amble using ideas from https://github.com/paul-gauthier/aider/blob/main/aider/coders/udiff_prompts.py
# Doesn't regress on the benchmark but improves average code generated and avoids empty comments.

# Add COT to each tool

instructions = """You are an expert software developer tasked with editing code to fulfill the user's request. Your goal is to make the necessary changes to the codebase while following best practices and respecting existing conventions. 

To complete the task, follow these steps:

1. Carefully analyze the user's request to identify the key requirements and changes needed. Break down the problem into smaller sub-tasks.

2. Search the codebase for relevant files, functions, classes, and variables related to the task at hand. Use the search results to determine where changes need to be made. 

3. For each relevant file, identify the minimal code changes required to implement the desired functionality. Consider edge cases, error handling, and necessary imports.

4. If new functionality is required that doesn't fit into existing files, create a new file with an appropriate name and location.

5. Make the code changes in a targeted way:
   - Preserve existing whitespace, comments and code style
   - Make surgical edits to only the required lines of code
   - If a change is complex, break it into smaller incremental changes
   - Ensure each change is complete and functional before moving on

6. When providing code snippets, be extremely precise with indentation:
   - Count the exact number of spaces used for indentation
   - If tabs are used, specify that explicitly 
   - Ensure the indentation of the code snippet matches the original file exactly
7. After making all the changes, review the modified code to verify it fully satisfies the original request.
8. Once you are confident the task is complete, submit the final solution.

In this environment, you have access to the following tools to assist in fulfilling the user request:

You MUST call them like this:
<function_calls>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_calls>

Here are the tools available:
<tools>
<tool_description>
<tool_name>analyze_problem_and_propose_plan</tool_name>
<description>
Carefully analyze the user's request to identify the key requirements, changes needed, and any constraints or considerations. Break down the problem into sub-tasks.
</description>
<parameters>
<parameter>
<name>problem_analysis</name>
<type>str</type>
<description>
Provide a thorough analysis of the user's request, identifying key details, requirements, intended behavior changes, and any other relevant information. Organize and prioritize the sub-tasks needed to fully address the request.
</description>
</parameter>
<parameter>
<name>proposed_plan</name>
<type>str</type>
<description>
Describe the plan to solve the problem, including the keywords to search, modifications to make, and all required imports to complete the task.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>search_codebase</tool_name>
<description>
Search the codebase for files, functions, classes, or variables relevant to a task. Searches can be scoped to a single file or across the entire codebase.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Explain why searching for this query is relevant to the task and how the results will inform the code changes.
</description>
</parameter>
<parameter>
<name>file_name</name>
<type>str</type>
<description>
(Optional) The name of a specific file to search within. If not provided, the entire codebase will be searched.
</description>
</parameter>
<parameter>
<name>keyword</name>
<type>str</type>
<description>
The search query, such as a function name, class name, or variable. Provide only one query term per search.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>analyze_and_identify_changes</tool_name>
<description>
Determine the minimal code changes required in a file to implement a piece of the functionality. Consider edge cases, error handling, and necessary imports.
</description>
<parameters>
<parameter>
<name>file_name</name>
<type>str</type>
<description>
The name of the file where changes need to be made.
</description>
</parameter>
<name>changes</name>
<type>str</type>
<description>
Describe the changes to make in the file. Specify the location of each change and provide the code modifications. Include any required imports or updates to existing code.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>view_file</tool_name>
<description>
View the contents of a file from the codebase. Useful for viewing code in context before making changes.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Explain why viewing this file is necessary to complete the task or better understand the existing code.
</description>
</parameter>
<parameter>
<name>file_name</name>
<type>str</type>
<description>
The name of the file to retrieve, including the extension. File names are case-sensitive.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>make_change</tool_name>
<description>
Make a SINGLE, TARGETED code change in a file. Preserve whitespace, comments and style. Changes should be minimal, self-contained and only address one specific modification. If a change requires modifying multiple separate code sections, use multiple calls to this tool, one for each independent change.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Explain how this SINGLE change contributes to fulfilling the user's request.
</description>
</parameter>
<parameter>
<name>file_name</name>
<type>str</type>
<description>
Name of the file to make the change in. Ensure correct spelling as this is case-sensitive.
</description>
</parameter>
<parameter>
<name>original_code</name>
<type>str</type>
<description>
The existing lines of code that need to be modified or replaced. This should be a SINGLE, CONTINUOUS block of code, not multiple separate sections. Include unchanged surrounding lines for context, but keep this
block AS SMALL AS POSSIBLE. This block should not be longer than 10 lines of code!
</description>
</parameter>
<parameter>
<name>new_code</name>
<type>str</type>
<description>
The new lines of code to replace the original code, implementing the SINGLE desired change. If the change is complex, break it into smaller targeted changes and use separate make_change calls for each.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>create_file</tool_name>
<description>
Create a new code file in the specified location with the given file name and extension. This is useful when the task requires adding entirely new functionality or classes to the codebase.
</description>
<parameters>
<parameter>
<name>file_path</name>
<type>str</type>
<description>
The path where the new file should be created, relative to the root of the codebase. Do not include the file name itself.
</description>
</parameter>
<parameter>
<name>file_name</name>
<type>str</type>
<description>
The name to give the new file, including the extension. Ensure the name is clear, descriptive, and follows existing naming conventions.
</description>
</parameter>
<parameter>
<parameter>
<name>contents</name>
<type>str</type>
<description>
The contents of this new file.
</description>
</parameter>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Explain why creating this new file is necessary to complete the task and how it fits into the existing codebase structure.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>submit_result</tool_name>
<description>
Indicate that the task is complete and all requirements have been satisfied. Provide the final code changes or solution.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Summarize the code changes made and how they fulfill the user's original request. Provide the complete, modified code if applicable.
</description>
</parameter>
</parameters>
</tool_description>
"""
reflection_prompt_prefix = """
CRITICAL FEEDBACK - READ CAREFULLY AND ADDRESS ALL POINTS
<critical_feedback_to_address>
Here is the feedback from your previous attempt. You MUST read this extremely carefully and follow ALL of the reviewer's advice. If you do not fully address this feedback you will fail to correctly solve the user's request.
{all_reflections}
</critical_feedback_to_address>"""

reflection_prompt = """<attempt_and_feedback_{idx}>
<previous_files_editted>
Edits to files from previous attempts:
{files_editted}
</previous_files_editted>
<rating>
Rating from previous attempt: {score} / 10
</rating>
<feedback>
Reviewer feedback on previous attempt:
{reflections_string}
</feedback>
</attempt_and_feedback_{idx}>"""

NO_TOOL_CALL_PROMPT = """FAILURE
No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:

<function_calls>
<invoke>
<tool_name>tool_name</tool_name>
<parameters>
<param_name>param_value</param_name>
</parameters>
</invoke>
</function_calls>

Here is an example:

<function_calls>
<invoke>
<tool_name>analyze_problem_and_propose_plan</tool_name>
<parameters>
<problem_analysis>The problem analysis goes here</problem_analysis>
<proposed_plan>The proposed plan goes here</proposed_plan>
</parameters>
</invoke>
</function_calls>

If you are really done, call the submit function.
"""

unformatted_tool_call_response = "<function_results>\n<result>\n<tool_name>{tool_name}<tool_name>\n<stdout>\n{tool_call_response_contents}\n</stdout>\n</result>\n</function_results>"


def int_to_excel_col(n):
    result = ""
    if n == 0:
        result = "A"
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def excel_col_to_int(s):
    result = 0
    for char in s:
        result = result * 26 + (ord(char) - 64)
    return result - 1

TOOLS_MAX_CHARS = 20000

def build_keyword_search_match_results(
    match_indices: list[int], # list of all indices where keyword appears in file_contents
    file_contents: str,
    keyword: str,
    starter_message: str,
) -> str:
    file_lines = file_contents.split("\n")
    file_lines_length = [len(line) for line in file_lines]
    # actual code lines
    all_matches = []
    # index of match
    match_line_indices = []
    # for each match
    for match_index in match_indices:
        # find correct row
        running_sum = 0
        for i in range(len(file_lines)):
            if match_index >= running_sum and match_index <= running_sum + file_lines_length[i]:
                match_display = (
                    f"{file_lines[i]}\n"
                    + " " * (match_index - running_sum)
                    + "^" * len(keyword)
                    + "\n"
                )
                match_line_indices.append(i)
                break
            running_sum += file_lines_length[i] + 1
        match_display = match_display.strip("\n")

        all_matches.append(f"\n{match_display}")
    
    # gather context lines around each match
    context_lines_index = []
    extra_lines = 40 # configurable value about how many lines to include around each match
    for index in match_line_indices:
        for i in range(max(0, index - extra_lines), min(index + extra_lines + 1, len(file_lines))):
            context_lines_index.append(i)
    
    context_lines_index = sorted(list(set(context_lines_index)))
    success_message = ""
    for i in range(len(context_lines_index)):
        line_index = context_lines_index[i]
        # see if we should print ...
        if i == 0: # first context line
            if line_index != 0:
                success_message += "\n..."
        if line_index in match_line_indices: # print match
            all_matches_index = match_line_indices.index(line_index)
            success_message += f"{all_matches[all_matches_index]}"
        else: # print context line
            success_message += f"\n{file_lines[line_index]}"
        
        # last context line
        if i == len(context_lines_index) - 1:
            if line_index != len(file_lines) - 1:
                success_message += "\n..."
        else:
            next_line_index = context_lines_index[i + 1]
            if next_line_index - 1 != line_index:
                success_message += "\n..."

    return starter_message + f"\n{success_message}"


def english_join(items: list[str]) -> str:
    if len(items) == 0:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"

def generate_status_message(file_path: str, fcrs: list[FileChangeRequest]) -> str:
    if not fcrs or len(fcrs) == 1:
        return f"You will resolve the issue by editing {file_path}."
    index = -1
    for i, fcr in enumerate(fcrs):
        if fcr.filename == file_path:
            index = i
            break
    else:
        logger.warning(f"Could not find file {file_path} in list of FCRs.")
        return f"You will resolve the issue by editing {file_path}."
    message = ""
    if index > 1:
        message += f"You have already made changes to {english_join([fcr.filename for fcr in fcrs[:index]])}. "
    message += f"You will resolve the issue by editing {file_path}. "
    if index < len(fcrs) - 1:
        message += f"You will edit the files {english_join([fcr.filename for fcr in fcrs[index + 1:]])} later."
    return message.strip()

# returns formatted response
def create_tool_call_response(tool_name: str, tool_call_response_contents: str) -> str:
    return unformatted_tool_call_response.replace("{tool_name}", tool_name).replace("{tool_call_response_contents}", tool_call_response_contents)

def default_dict_value():
    return {"contents": "", "original_contents": ""}

# returns dictionary of all changes made
@file_cache(ignore_params=["file_path", "chat_logger", "cloned_repo", "assistant_id", "ticket_progress", "assistant_conversation", "cwd"])
def function_modify(
    fcrs: list[FileChangeRequest],
    request: str,
    cloned_repo: ClonedRepo,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = None,
    ticket_progress: TicketProgress | None = None,
    assistant_conversation: AssistantConversation | None = None,
    seed: int = None,
    relevant_filepaths: list[str] = [],
    cwd: str | None = None,
    previous_modify_files_dict: dict[str, dict[str, str]] = None,
    reflections: str = "",
) -> dict[str, dict[str, str]] | None:
    try:
        logger.info("Starting function_modify_unstable")
        def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
            if assistant_conversation:
                assistant_conversation.update_from_ids(
                    assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
                )
            ticket_progress.save()
        # a complete history of messages between the assistant and the user
        complete_message_history: list[dict[str, str]] = []
        # dictionary mapping a file path to various data used in modify, this needs to be stateful, so it is possible that previous_modify_files_dict
        modify_files_dict = previous_modify_files_dict or defaultdict(default_dict_value)
        cwd = cwd or cloned_repo.repo_dir
        # current_contents = contents_of_file
        sweep_config: SweepConfig = SweepConfig()
        # current_file_to_modify_contents = f"<current_file_to_modify filename=\"{file_path}\">\n{chunked_file_contents}\n</current_file_to_modify>"
        # fcrs_message = generate_status_message(file_path, fcrs)
        relevant_file_paths_string = ", ". join(relevant_filepaths) 
        combined_request_unformatted = "In order to solve the user's request you will need to modify/create the following files:\n\n{files_to_modify}\n\nThe order you choose to modify/create these files is up to you.\n"
        files_to_modify = ""
        for fcr in fcrs:
            files_to_modify += f"\n\nYou will need to {fcr.change_type} {fcr.filename}, the specific instructions to do so are listed below:\n\n{fcr.instructions}"
        combined_request_message = combined_request_unformatted.replace("{files_to_modify}", files_to_modify.lstrip('\n'))
        new_additional_messages = [
            Message(
                role="user",
                content=f"# Request\n{request}",
            ),
            Message(
                role="user",
                content=f"\n{combined_request_message}",
            )
        ]
        if relevant_file_paths_string:
            new_additional_messages.append(Message(
                role="user",
                content=f'You should view the following relevant files: {relevant_file_paths_string}\n\nREMEMBER YOUR END GOAL IS TO SATISFY THE # Request'
            ))
        additional_messages = additional_messages + new_additional_messages
        # if we have reflections
        if reflections:
            additional_messages = [*additional_messages,
                                   Message(role="user", content=reflections)]

        initial_check_results: dict[str, CheckResults] = {}
        # add any already made changes to the additional_messages
        for file_path, file_data in modify_files_dict.items():
            diff = generate_diff(file_data["original_contents"], file_data["contents"])
            if diff:
                additional_messages.append(
                    Message(
                        role="user",
                        content=f"The following changes in {file_path} have already been applied in an attempt to address this problem:\n```\n"
                        + diff
                        + "\n```",
                    )
                )
            # go through any already made changes and generate the intial_check_results
            initial_check_results[file_path] = get_check_results(file_path, file_data['original_contents'])
        assistant_generator = openai_assistant_call(
            request="",  # already present in additional_messages
            instructions=instructions,
            additional_messages=ensure_additional_messages_length(additional_messages),
            chat_logger=chat_logger,
            assistant_id=assistant_id,
            save_ticket_progress=(
                save_ticket_progress if ticket_progress is not None else None
            ),
            assistant_name="Code Modification Function Assistant",
            tools=[],
        )
        # we add to complete_message_history this way to prevent unforseen mutations to additional_messages
        complete_message_history.extend([*additional_messages])
        try:
            done_counter = 0
            tool_name, tool_call, llm_response = assistant_generator.send(None)
            for i in range(100):  # TODO: tune this parameter
                # append all responses from the llm
                complete_message_history.append(llm_response)
                print(tool_name, json.dumps(tool_call, indent=2))
                if tool_name == "done":
                    changes_made = False
                    # iterate through modify_files_dict and generate diffs
                    diffs_made = defaultdict(str)
                    for file_name, file_data in modify_files_dict.items():
                        new_contents = file_data["contents"]
                        original_contents = file_data["original_contents"]
                        diff = generate_diff(original_contents, new_contents)
                        if diff:
                            changes_made = True
                            diffs_made[file_name] = diff

                    if changes_made:
                        break
                    else:
                        done_counter += 1
                        if done_counter >= 3:
                            break
                        error_message = create_tool_call_response("submit_result", "ERROR\n\nNo changes were made. Please continue working on your task.")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            error_message
                        )
                        complete_message_history.append({"role": "user", "content": error_message})              
                elif tool_name == "no_tool_call":
                    error_message = ""
                    tool_name, tool_call, llm_response = assistant_generator.send(
                        NO_TOOL_CALL_PROMPT
                    )
                    complete_message_history.append({"role": "user", "content": NO_TOOL_CALL_PROMPT})  
                elif tool_name == "analyze_problem_and_propose_plan":
                    error_message = ""
                    success_message = create_tool_call_response(tool_name, "SUCCESS\n\nSounds like a great plan! Lets get started!")
                    tool_name, tool_call, llm_response = assistant_generator.send(
                        success_message
                    )
                    complete_message_history.append({"role": "user", "content": success_message})
                elif tool_name == "analyze_and_identify_changes":
                    error_message = ""
                    # make sure the change is for an existing or newly created file
                    if "file_name" not in tool_call:
                        error_message = "Missing file_name in tool call. Call the tool again but this time provide the file_name."
                    if not error_message:
                        file_name = tool_call["file_name"].strip()
                        if not os.path.exists(os.path.join(cwd, file_name)) and file_name not in modify_files_dict:
                            error_message = f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!"
                    if not error_message:
                        success_message = create_tool_call_response(tool_name, "SUCCESS\n\nNice work! Now use the make_change tool to make the listed changes one at a time. If there are multiple changes required, call the make_change tool multiple times.")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            success_message
                        )
                        complete_message_history.append({"role": "user", "content": success_message})
                    else:
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            error_message
                        )
                        complete_message_history.append({"role": "user", "content": error_message})
                elif tool_name == "view_file":
                    error_message = ""
                    file_name = tool_call["file_name"].strip()
                    full_file_name = os.path.join(cwd, file_name)
                    # not in code base and not created
                    if not os.path.exists(full_file_name) and file_name not in modify_files_dict:
                        similar_file_paths = "\n".join(
                            [
                                f"- {path}"
                                for path in cloned_repo.get_similar_file_paths(
                                    file_name
                                )
                            ]
                        )
                        error_message = f"The file {file_name} does not exists. {'Did you mean one of the following files?' if similar_file_paths else ''}\n{similar_file_paths}"
                    if not error_message:
                        # if this is the first time viewing this file
                        if file_name not in modify_files_dict:
                            try:
                                file_contents = read_file_with_fallback_encodings(full_file_name)
                            except Exception as e:
                                logger.error(f"Error occured while attempting to read the file {file_name}: {e}")
                                error_message = f"Error occured while attempting to read the file {file_name}: {e}"
                            if not error_message:
                                # update data for this file inside modify_files_dict unless it already exists
                                modify_files_dict[file_name] = {"contents": file_contents, "original_contents": file_contents}
                                initial_check_results[file_name] = get_check_results(file_name, file_contents)
                        else:
                            # filename already exists in modify_files_dict, implies edits were made to it
                            file_contents = modify_files_dict[file_name]["contents"]
                        logger.debug(f'SUCCESS\n\nHere is the file:\n\n<file filename="{file_name}">\n{file_contents}\n</file filename="{file_name}">')
                        success_message = create_tool_call_response(tool_name, f'SUCCESS\n\nHere is the file:\n\n<file filename="{file_name}">\n{file_contents}\n</file filename="{file_name}">')
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            success_message
                        )
                        complete_message_history.append({"role": "user", "content": success_message})
                    if error_message:
                        logger.debug(f"ERROR in view_file\n\n{error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            error_message
                        )
                        complete_message_history.append({"role": "user", "content": error_message})
                elif tool_name == "make_change":
                    error_message = ""
                    for key in ["file_name", "original_code", "new_code"]:
                        if key not in tool_call:
                            error_message += f"Missing {key} in tool call.Call the tool again but this time provide the {key}.\n"
                            # special case where original_code is so long it forgets new_code
                            if key == "new_code" or key == "original_code":
                                error_message += f"\n\nIt is likely the reason why you have missed these keys is because the original_code you provided is WAY TOO LARGE and as such you have missed the closing xml tags. REDUCE the original_code block to be under 10 lines of code!"
                    for _ in range(1): # this is super jank code but it works for now - only for easier error message handling
                        # ensure the file we are editting exists and is in modify_files_dict
                        if "file_name" in tool_call:
                            file_name = tool_call["file_name"].strip()
                            # if not in codebase or has not been created
                            if not os.path.exists(os.path.join(cwd, file_name)) and file_name not in modify_files_dict:
                                error_message += f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!\n"
                            if file_name not in modify_files_dict:
                                error_message += f"You have not viewed {file_name} yet! Are you CERTAIN this is the file you want to modify? If so, view the file first with the view_file tool and then call the make_change tool again.\n"
                        if error_message:
                            break
                        success_message = ""
                        original_code = tool_call["original_code"].strip("\n")
                        new_code = tool_call["new_code"].strip("\n")
                        if new_code == original_code:
                            error_message += "The new_code and original_code are the same. Are you CERTAIN this change needs to be made? If you are certain this change needs to be made, MAKE SURE that the new_code and original_code are NOT the same."
                            break
                        # get the contents for the file
                        file_contents = modify_files_dict[file_name]['contents']
                        warning_message = ""
                        
                        # handle special case where there are \r\n characters in the current chunk as this will cause search and replace to ALWAYS fail
                        if "\r\n" in file_contents:
                            # replace in current chunk
                            file_contents = file_contents.replace("\r\n", "\n")
                        # check to see that the original_code is in the new_code by trying all possible indentations
                        correct_indent, rstrip_original_code = manual_code_check(file_contents, original_code)
                        # if the original_code couldn't be found in the chunk we need to let the llm know
                        if original_code not in file_contents and correct_indent == -1:
                            error_message = f"The original_code provided does not appear to be present in file {file_name}. The original_code contains:\n```\n{original_code}\n```\nBut this section of code was not found anywhere inside the current file. DOUBLE CHECK that the change you are trying to make is not already implemented in the code!"
                            # first check the lines in original_code, if it is too long, ask for smaller changes
                            original_code_lines_length = len(original_code.split("\n"))
                            if original_code_lines_length > 7:
                                error_message += f"\n\nThe original_code seems to be quite long with {original_code_lines_length} lines of code. Break this large change up into a series of SMALLER changes to avoid errors like these! Try to make sure the original_code is under 7 lines. DOUBLE CHECK to make sure that this make_change tool call is only attempting a singular change, if it is not, make sure to split this make_change tool call into multiple smaller make_change tool calls!"
                            else:
                                # generate the diff between the original code and the current chunk to help the llm identify what it messed up
                                # chunk_original_code_diff = generate_diff(original_code, current_chunk) - not necessary
                                error_message += "\n\nDOUBLE CHECK that the original_code you have provided is correct, if it is not, correct it then make another replacement with the corrected original_code. The original_code MUST be in section A in order for you to make a change. DOUBLE CHECK to make sure that this make_change tool call is only attempting a singular change, if it is not, make sure to split this make_change tool call into multiple smaller make_change tool calls!"
                            break
                        # ensure original_code and new_code has the correct indents
                        new_code_lines = new_code.split("\n")
                        new_code = "\n".join(f'{correct_indent*" "}{line}' for line in new_code_lines)
                        if rstrip_original_code:
                            original_code_lines = [line.rstrip() for line in original_code.split("\n")]
                        else:
                            original_code_lines = original_code.split("\n")
                        original_code = "\n".join(f'{correct_indent*" "}{line}' for line in original_code_lines)
                        # before we apply changes make sure original_code is unique inside current_chunk
                        current_chunk_occurences = file_contents.count(original_code)
                        if current_chunk_occurences > 1:
                            error_message = f"The original_code is not unique in the file {file_name}. It appears {current_chunk_occurences} times! original_code MUST be unique, add some more lines for context!"
                            break

                        # apply changes
                        new_file_contents = file_contents.replace(original_code, new_code, 1)
                        # Check if changes were made
                        if new_file_contents == file_contents:
                            logger.warning("No changes were made to the code.")
                            error_message = "No changes were made, it seems the changes you requested were not applied or made no difference to the code file."
                            break
                        
                        # Check if the changes are valid
                        if not error_message:
                            check_results = get_check_results(file_name, new_file_contents)
                            # check_results_message = check_results.is_worse_than_message(initial_check_results) - currently unused
                            failing_parse = check_results.parse_error_message if not initial_check_results[file_name].parse_error_message else ""
                            current_diff = generate_diff(
                                file_contents, new_file_contents
                            )
                            if failing_parse:
                                error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code with the following error logs:\n{failing_parse}\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the make_change tool with different changes that yield valid code."
                                break
                    if error_message:
                        logger.error(f"ERROR occured in make_change tool: {error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            error_message
                        )
                        complete_message_history.append({"role": "user", "content": error_message})
                    if not error_message:
                        success_message = (
                            f"SUCCESS\n\nThe following changes have been applied to {file_name}:\n\n"
                            + generate_diff(file_contents, new_file_contents)
                        ) + f"{warning_message}\n\nYou can continue to make changes to the file {file_name} and call the make_change tool again, or go back to searching for keywords using the search_codebase tool, which is great for finding all definitions or usages of a function or class. REMEMBER to add all necessary imports at the top of the file, if the import is not already there!"
                        # set contents
                        modify_files_dict[file_name]['contents'] = new_file_contents
                        logger.info(success_message)

                        success_message = create_tool_call_response(tool_name, f"SUCCESS\n\n{success_message}")
                        
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            success_message
                        )
                        complete_message_history.append({"role": "user", "content": success_message})
                elif tool_name == "create_file":
                    error_message = ""
                    success_message = ""
                    for key in tool_call_parameters[tool_name]:
                        if key not in tool_call:
                            logger.debug(f"No {key} was provided in the {tool_name} tool call. Call the tool again but this time provide the {key}.")
                            error_message += f"No {key} was provided in the {tool_name} tool call. Call the tool again but this time provide the {key}.\n"
                    if not error_message:
                        new_file_path = tool_call["file_path"].strip()
                        new_file_name = tool_call["file_name"].strip()
                        new_file_contents = tool_call["contents"].strip()
                        new_file_dir = os.path.join(cwd, new_file_path)
                        new_full_file_path = os.path.join(new_file_path, new_file_name)
                        new_full_file_path_with_cwd = os.path.join(cwd, new_file_path, new_file_name)
                        # ensure file doesn't already exist
                        if os.path.exists(new_full_file_path_with_cwd):
                            error_message = f"The file {new_full_file_path} already exists. Modify this existing file instead of attempting to create a new one!"
                        # ensure directory is valid
                        if not os.path.isdir(new_file_dir):
                            error_message = f"The directory {new_file_path} is not valid. Make sure you have the correct directory path!"
                        # ensure that the directory of the new full path exists, in case the file name is weird
                        if not os.path.exists(os.path.dirname(new_full_file_path_with_cwd)):
                            error_message = f"The directory {os.path.dirname(new_full_file_path)} does not exist. Make sure you the new file you want to create exists within an existing directory!"
                        # if no issues, create the file by placing it in modify_files_dict
                        if not error_message:
                            modify_files_dict[new_full_file_path] = {"contents": new_file_contents, "original_contents": ""}
                            success_message = f"The new file {new_full_file_path} has been created successfully with the following contents:\n\n{new_file_contents}"
                    if error_message:
                        logger.debug(f"ERROR occured in create_file tool: {error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            error_message
                        )
                        complete_message_history.append({"role": "user", "content": error_message})
                    else:
                        logger.debug(f"SUCCESS\n\n{success_message}")
                        success_message = create_tool_call_response(tool_name, f"SUCCESS\n\n{success_message}")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            success_message
                        )
                        complete_message_history.append({"role": "user", "content": success_message})
                elif tool_name == "search_codebase":
                    error_message = ""
                    success_message = ""
                    for key in ["keyword"]:
                        if key not in tool_call:
                            logger.debug(f"No {key} was provided in the search_codebase tool call. Call the tool again but this time provide the {key}.")
                            error_message += f"No {key} was provided in the search_codebase tool call. Call the tool again but this time provide the {key}.\n"

                    file_name = ""
                    if "file_name" in tool_call:
                        file_name = tool_call["file_name"].strip()
                        # see if we are searching the whole codebase or not
                        if file_name: # search specific file
                            full_file_path = os.path.join(cwd, file_name)
                            # not in codebase and also not a newly created file
                            if not os.path.exists(full_file_path) and file_name not in modify_files_dict:
                                logger.debug(f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!")
                                error_message = f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!"
                            # make sure it is a file and not a directory
                            elif os.path.isdir(full_file_path):
                                logger.debug(f"The file {file_name} is a directory. Make sure you are providing a file name!")
                                error_message += f"The file {file_name} is a directory. Make sure you are providing a file name!"
                            
                    # if no issues continue with search
                    if not error_message:
                        keyword = tool_call["keyword"].strip()
                        # search specific file
                        if file_name:
                            logger.info(f"Searching for keyword {keyword} in file {file_name}")
                            match_indices = []
                            # if the current code file is not in the modify_files_dict, add it
                            if file_name not in modify_files_dict:
                                file_contents = read_file_with_fallback_encodings(full_file_path)
                                modify_files_dict[file_name] = {"contents": file_contents, "original_contents": file_contents}
                                initial_check_results[file_name] = get_check_results(file_name, file_contents)
                            # get contents
                            file_contents = modify_files_dict[file_name]["contents"]
                            match_count = file_contents.count(keyword)

                            # if there are no matches
                            if match_count == 0:
                                logger.debug(f"The search term {keyword} does not appear to be present in the file: {file_name}. Consider missing or misplaced whitespace, comments or delimiters in the keyword.")
                                error_message = f"The search term {keyword} does not appear to be present in the file: {file_name}. Consider missing or misplaced whitespace, comments or delimiters in the keyword."
                            else:
                                match_indices = get_all_indices_of_substring(file_contents, keyword)
                                # for matches inside current code file
                                starter_message = f"The keyword {keyword} was found {match_count} {'time' if match_count == 1 else 'times'} in the file {file_name}. They appear in the following places:\n\n"
                                success_message += (
                                    build_keyword_search_match_results(
                                        match_indices,
                                        file_contents,
                                        keyword,
                                        starter_message
                                    )
                                )
                        else: # search whole codebase
                            logger.info(f"Searching for keyword {keyword} in the entire codebase.")
                            rg_command = ["rg", "-n", "-i" , f'"{keyword}"', cwd]
                            try:
                                # update the cloned repo before running ripgrep as it is possible some of the files have been editted
                                for file_name, file_data in modify_files_dict.items():
                                    updated = update_file(cloned_repo.repo_dir, file_name, file_data["contents"])
                                    if not updated:
                                        raise Exception(f"Failed to update file {file_name} in the cloned repo.")
                            except Exception as e:
                                logger.error(f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}")
                                error_message = f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}\n"
                                # attempt to undo the updates
                                for file_name, file_data in modify_files_dict.items():
                                    update_file(cloned_repo.repo_dir, file_name, file_data["original_contents"])
                                
                            try:
                                result = subprocess.run(" ".join(rg_command), text=True, shell=True, capture_output=True)
                                output = result.stdout
                                if output:
                                    # post process rip grep output to be more condensed
                                    rg_output_pretty, _ = post_process_rg_output(cwd, sweep_config, output)
                                    if not rg_output_pretty:
                                        error_message += f"FAILURE: No results found for keyword: {keyword} in the entire codebase. Please try a new keyword. If you are searching for a function definition try again with different whitespaces.\n"
                                else:
                                    error_message += f"FAILURE: No results found for keyword: {keyword} in the entire codebase. Please try a new keyword. If you are searching for a function definition try again with different whitespaces.\n"
                            except Exception as e:
                                logger.error(f"FAILURE: An Error occured while trying to reset the cloned repo on file {file_name}: {e}\n")
                                error_message += f"FAILURE: An Error occured while trying to rest the cloned repo on file {file_name}: {e}\n"

                            try:
                                # reset cloned_repo to original state
                                for file_name, file_data in modify_files_dict.items():
                                    updated = update_file(cloned_repo.repo_dir, file_name, file_data["original_contents"])
                                    if not updated:
                                        raise Exception(f"Failed to update file {file_name} in the cloned repo.")
                            except Exception as e:
                                logger.error(f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}")
                                error_message = f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}"

                            if not error_message:
                                success_message = f"Here are the search_codebase results:\n{rg_output_pretty}\n\n You can use these results to revise your plan by calling the analyze_problem_and_propose_plan tool again. You can also call the analyze_and_identify_changes tool again."
                            else:
                                # if all of the above has failed it is possible that it is attmepting to search for a file name
                                similar_file_paths = cloned_repo.get_similar_file_paths(keyword)
                                similar_file_paths = [path for path in similar_file_paths if path.strip()]
                                if not similar_file_paths:
                                    error_message += f"FAILURE: No file paths were found in the codebase that resemble {keyword}. Please try again!"
                                else:
                                    similar_file_paths_string = "\n".join([f"- {path}" for path in similar_file_paths])
                                    error_message = ""
                                    success_message = f"Here are some files that exist in the code base that resemble the keyword {keyword}:\n{similar_file_paths_string}\n\nYou can use use the view_file tool to explore a file in more detail."

                    if error_message:
                        logger.debug(f"ERROR in search_codebase\n\n{error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            error_message
                        )
                        complete_message_history.append({"role": "user", "content": error_message})
                    else:
                        logger.debug(success_message)
                        suffix = "\n\nMake additional search_codebase calls to find other keywords or start making changes by calling the make_change tool."
                        success_message = create_tool_call_response(tool_name, f"SUCCESS\n\n{success_message}{suffix}")
                        tool_name, tool_call, llm_response = assistant_generator.send(
                            success_message
                        )
                        complete_message_history.append({"role": "user", "content": success_message})
                else:
                    error_message = create_tool_call_response("UNKNOWN TOOL NAME", f"ERROR\nUnexpected tool name: {tool_name}")
                    tool_name, tool_call, llm_response = assistant_generator.send(
                        error_message
                    )
                    complete_message_history.append({"role": "user", "content": error_message})
            else:
                logger.error("Too many iterations.")
        except StopIteration:
            pass
        # return dictionary of file paths to their new contents
        changes_made = False
        diffs_made = defaultdict(str)
        unmodified_files = []
        for file_name, file_data in modify_files_dict.items():
            diff = generate_diff(file_data["original_contents"], file_data["contents"])
            if diff:
                changes_made = True
                diffs_made[file_name] = diff
            else:
                # remove this file from the dictionary
                unmodified_files.append(file_name)
        # remove any unmodified files
        for file_name in unmodified_files:
            modify_files_dict.pop(file_name)
            logger.info(f"Removing {file_name} from modify_files_dict as no changes were made to this file.")

        if changes_made:
            for file_name, diff in diffs_made.items():
                logger.info(f"Changes made to {file_name}:\n\n{diff}")
        else:
            logger.warning("No changes were made.")
        if changes_made:
            logger.info("Finished modifying files!")
            return modify_files_dict, complete_message_history
    except AssistantRaisedException as e:
        logger.exception(e)
        discord_log_error(
            str(e)
            + "\n\n"
            + traceback.format_exc()
            + "\n\n"
            + str(chat_logger.data if chat_logger else "")
            + "\n\n"
            + str(ticket_progress.tracking_id if ticket_progress else "")
        )
    except Exception as e:
        logger.exception(e)
        # TODO: Discord
        discord_log_error(
            str(e)
            + "\n\n"
            + traceback.format_exc()
            + "\n\n"
            + str(chat_logger.data if chat_logger else "")
            + "\n\n"
            + str(ticket_progress.tracking_id if ticket_progress else "")
        )
        return None, complete_message_history
    return None, complete_message_history

def create_reflections_for_modify(rollout_evaluations: list[tuple[int, dict[str, dict[str, str]]], str]) -> str:
    reflections = ""
    for i, (score, changed_files_dict, message_to_contractor) in enumerate(rollout_evaluations):
        files_editted = ""
        for file_path, file_data in changed_files_dict.items():
            diff = generate_diff(file_data["original_contents"], file_data["contents"])
            files_editted += f"Changes made to file {file_path}:\n{diff}\n\n"
        reflections += reflection_prompt.format(idx=i + 1, files_editted=files_editted, score=score, reflections_string=message_to_contractor)
    return reflection_prompt_prefix.format(all_reflections=reflections)

# perform some number of rollouts of function_modify, evaluates each roll out and picks the best performing one
# stops rolling out when max rollouts is reached or a score is above accept threshold
def self_eval_modify(
    fcrs: list[FileChangeRequest],
    request: str,
    cloned_repo: ClonedRepo,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = None,
    ticket_progress: TicketProgress | None = None,
    assistant_conversation: AssistantConversation | None = None,
    seed: int = None,
    relevant_filepaths: list[str] = [],
    cwd: str | None = None,
    previous_modify_files_dict: dict[str, dict[str, str]] = None
    ):
    MAX_NUM_ROLLOUTS = 2
    SCORE_THRESHOLD = 8
    rollout_evaluations: list[tuple[int, dict[str, dict[str, str]], str]] = []
    previous_reflections = ""
    previous_modify_files_dict = {}
    for rollout in range(MAX_NUM_ROLLOUTS):
        changed_files_dict, complete_message_history = function_modify( fcrs, request, cloned_repo, additional_messages, chat_logger, assistant_id, ticket_progress, assistant_conversation, seed, relevant_filepaths, cwd, previous_modify_files_dict, previous_reflections)
        truncated_message_results = complete_message_history[1:] # skip system prompt
        joined_messages = ""
        for message in truncated_message_results:
            if isinstance(message, dict):
                joined_messages += f"{message['role']}:\n{message['content']}\n\n"
            else:
                joined_messages += f"{message.role}:\n{message.content}\n\n"
        # evaluate the rollout
        if not changed_files_dict:
            score = None
        else:
            score, message_to_contractor = ModifyEvaluatorAgent().evaluate_run(problem_statement=request, run_text=joined_messages, changed_files=changed_files_dict)
        if score is None or message_to_contractor is None:
            continue # can't get any reflections here
        # update reflections
        previous_modify_files_dict = changed_files_dict
        rollout_evaluations.append((score, changed_files_dict, message_to_contractor))
        previous_reflections = create_reflections_for_modify(rollout_evaluations)
        if score >= SCORE_THRESHOLD:
            break
    # return best set of changes
    _, best_changes, _ = max(rollout_evaluations, key=lambda x: x[0] * 100)
    return best_changes 

if __name__ == "__main__":
    from sweepai.config.server import INSTALLATION_ID
    # request = "Convert any all logger.errors to logger.exceptions in on_ticket.py"
    request = """Split any logger.errors to:
logger = Logger()
logger.errors()
in on_ticket.py""" # this causes a pylint error so it's great for testing
    cloned_repo = ClonedRepo(
        repo_full_name="sweepai/sweep",
        installation_id=INSTALLATION_ID
    )
    additional_messages = [
        Message(
            role="user",
            content="# Repo & Issue Metadata\nRepo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.\nIssue Title: Convert any all logger.errors to logger.exceptions in on_ticket.py",
            name=None,
            function_call=None,
            key="issue_metadata",
        )
    ]
    file_contents = open("sweepai/handlers/on_ticket.py", "r").read()
    response = function_modify(
        request=request,
        file_path="sweepai/handlers/on_ticket.py",
        contents_of_file=file_contents,
        cloned_repo=cloned_repo,
        chat_logger=ChatLogger(
            {
                "username": "kevinlu1248",
                "title": request
            }
        ),
        additional_messages=additional_messages,
        ticket_progress=TicketProgress(tracking_id="test_remove_assistant_1"),
    )
