from copy import deepcopy
import copy
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
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.diff import generate_diff
from sweepai.utils.file_utils import read_file_with_fallback_encodings
from sweepai.utils.github_utils import ClonedRepo, update_file
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.utils import chunk_code, get_check_results
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
<name>section_id</name>
<type>str</type>
<description>
The section ID where the original code to be modified belongs to, helping to locate the specific area within the file.
</description>
</parameter>
<parameter>
<name>original_code</name>
<type>str</type>
<description>
The existing lines of code that need to be modified or replaced. This should be a SINGLE, CONTINUOUS block of code, not multiple separate sections. Include unchanged surrounding lines for context.
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
    match_indices: list[int],
    chunks: list[str],
    keyword: str,
    success_message,
    readonly: bool = False,
) -> str:
    for match_index in match_indices:
        # TODO: handle multiple matches in one line
        match = chunks[match_index]
        match_lines = match.split("\n")
        lines_containing_keyword = [
            i for i, line in enumerate(match_lines) if keyword in line
        ]
        cols_of_keyword = [
            match_lines[line_containing_keyword].index(keyword)
            for line_containing_keyword in lines_containing_keyword
        ]
        match_display = ""
        for i, line in enumerate(match_lines):
            if i in lines_containing_keyword:
                match_display += (
                    f"{line}\n"
                    + " " * (cols_of_keyword[lines_containing_keyword.index(i)])
                    + "^" * len(keyword)
                    + "\n"
                )
            else:
                match_display += f"{line}\n"
        match_display = match_display.strip("\n")
        num_matches_message = f" ({len(lines_containing_keyword)} matches)" if lines_containing_keyword else " (No keyword matches, just shown for context)"
        if not readonly:
            success_message += f"<section id='{int_to_excel_col(match_index + 1)}'>{num_matches_message}\n{match_display}\n</section>\n"
        else:
            success_message += f"<readonly_section id='{int_to_excel_col(match_index + 1)}>{num_matches_message}\n{match_display}\n</readonly_section>\n"
    return success_message


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
    return {"chunks": [], "contents": "", "original_contents": ""}

# returns dictionary of all changes made
@file_cache(ignore_params=["file_path", "chat_logger", "cloned_repo", "assistant_id", "ticket_progress", "assistant_conversation", "cwd"])
def function_modify(
    request: str,
    file_path: str,
    contents_of_file: str,
    cloned_repo: ClonedRepo,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = None,
    ticket_progress: TicketProgress | None = None,
    assistant_conversation: AssistantConversation | None = None,
    seed: int = None,
    relevant_filepaths: list[str] = [],
    cwd: str | None = None,
    fcrs: list[FileChangeRequest]=[],
    previous_modify_files_dict: dict[str, dict[str, str | list[str]]] = None,
) -> dict[str, dict[str, str | list[str]]] | None:
    try:
        logger.info("Starting function_modify_unstable")
        def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
            if assistant_conversation:
                assistant_conversation.update_from_ids(
                    assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
                )
            ticket_progress.save()
        # dictionary mapping a file path to various data used in modify, this needs to be stateful, so it is possible that previous_modify_files_dict
        modify_files_dict = previous_modify_files_dict or defaultdict(default_dict_value)
        cwd = cwd or cloned_repo.repo_dir
        current_contents = contents_of_file
        initial_check_results = get_check_results(file_path, current_contents)
        # save chunks and contents of file if its not already present
        if file_path not in modify_files_dict:
            original_snippets = chunk_code(current_contents, file_path, 1400, 500)
            file_contents_lines = current_contents.split("\n")
            chunks = [
                "\n".join(file_contents_lines[max(snippet.start - 1, 0) : snippet.end])
                for snippet in original_snippets
            ]
            modify_files_dict[file_path] = {"chunks": copy.deepcopy(chunks), "contents": current_contents, "original_contents": current_contents}
        sweep_config: SweepConfig = SweepConfig()
        chunked_file_contents = "\n".join(
            [
                f'<section id="{int_to_excel_col(i + 1)}">\n{chunk}\n</section id="{int_to_excel_col(i + 1)}>'
                for i, chunk in enumerate(modify_files_dict[file_path]["chunks"])
            ]
        )
        current_file_to_modify_contents = f"<current_file_to_modify filename=\"{file_path}\">\n{chunked_file_contents}\n</current_file_to_modify>"
        fcrs_message = generate_status_message(file_path, fcrs)
        relevant_file_paths_string = ", ". join(relevant_filepaths) 
        new_additional_messages = [
            Message(
                role="user",
                content=f"# Request\n{request}\n\n{fcrs_message}",
            ),
            Message(
                role="user",
                content=current_file_to_modify_contents,
            ),
        ]
        if relevant_file_paths_string:
            new_additional_messages.append(Message(
                role="user",
                content=f'You should view the following relevant files: {relevant_file_paths_string}'
            ))
        additional_messages = new_additional_messages + additional_messages
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

        try:
            done_counter = 0
            tool_name, tool_call = assistant_generator.send(None)
            for i in range(100):  # TODO: tune this parameter
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
                        tool_name, tool_call = assistant_generator.send(
                            error_message
                        )                  
                elif tool_name == "no_tool_call":
                    error_message = ""
                    tool_name, tool_call = assistant_generator.send(
                        "ERROR\n No tool calls were made. If you are done, please use the submit_result tool to indicate that you have completed the task. If you believe you are stuck, use the search_codebase tool to further explore the codebase or get additional context if necessary."
                    )
                elif tool_name == "analyze_problem_and_propose_plan":
                    error_message = ""
                    success_message = create_tool_call_response(tool_name, "SUCCESS\n\nSounds like a great plan! Let's get started.")
                    tool_name, tool_call = assistant_generator.send(
                        success_message
                    )
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
                        tool_name, tool_call = assistant_generator.send(
                            success_message
                        )
                    else:
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            error_message
                        )
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
                                error_message = f"Error occured while attempting to read the file {file_name}: {e}"
                            if not error_message:
                                # chunk the file
                                file_original_snippets = chunk_code(file_contents, file_name, 1400, 500)
                                view_file_contents_lines = file_contents.split("\n")
                                file_chunks = [
                                    "\n".join(view_file_contents_lines[max(snippet.start - 1, 0) : snippet.end])
                                    for snippet in file_original_snippets
                                ]
                                # update chunks for this file inside modify_files_dict unless it already exists
                                modify_files_dict[file_name] = {"chunks": copy.deepcopy(file_chunks), "contents": file_contents, "original_contents": file_contents}
                                chunked_file_contents = ""
                                for i, chunk in enumerate(file_chunks):
                                    idx = int_to_excel_col(i + 1)
                                    chunked_file_contents += f'\n<section id="{idx}">\n{chunk}\n</section id="{idx}">'
                        else:
                            # filename already exists in modify_files_dict, implies edits were made to it
                            chunked_file_contents = "\n".join(
                                [
                                    f'<section id="{int_to_excel_col(i + 1)}">\n{chunk}\n</section id="{int_to_excel_col(i + 1)}>'
                                    for i, chunk in enumerate(modify_files_dict[file_name]["chunks"])
                                ]
                            )
                        logger.debug(f'SUCCESS\n\nHere is the file:\n\n<file filename="{file_name}">\n{chunked_file_contents}\n</file filename="{file_name}">')
                        success_message = create_tool_call_response(tool_name, f'SUCCESS\n\nHere is the file:\n\n<file filename="{file_name}">\n{chunked_file_contents}\n</file filename="{file_name}">')
                        tool_name, tool_call = assistant_generator.send(
                            success_message
                        )
                    if error_message:
                        logger.debug(f"ERROR in ViewFile\n\n{error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            error_message
                        )
                elif tool_name == "make_change":
                    error_message = ""
                    for key in ["file_name", "section_id", "original_code", "new_code"]:
                        if key not in tool_call:
                            error_message += f"Missing {key} in tool call.Call the tool again but this time provide the {key}.\n"
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
                        section_letter = tool_call["section_id"].strip()
                        section_id = excel_col_to_int(section_letter)
                        original_code = tool_call["original_code"].strip("\n")
                        new_code = tool_call["new_code"].strip("\n")
                        if new_code == original_code:
                            error_message += "The new_code and original_code are the same. Are you CERTAIN this change needs to be made? If you are certain this change needs to be made, MAKE SURE that the new_code and original_code are NOT the same."
                            break
                        # get the chunks and contents for the file
                        file_chunks = deepcopy(modify_files_dict[file_name]['chunks'])  
                        file_contents = modify_files_dict[file_name]['contents']
                        warning_message = ""
                        if section_id >= len(file_chunks):
                            error_message = f"Could not find section {section_letter} in file {file_name}, which has {len(file_chunks)} sections."
                            break
                        elif section_id < 0:
                            error_message = f"The section id {section_letter} can not be parsed."
                            break

                        # fetch the chunk of code we will be modifying
                        try:
                            current_chunk = file_chunks[section_id]
                        except Exception:
                            error_message = f"Could not fetch the chunk of code for section {section_letter} in file {file_name}. Make sure you are modifying the correct file: {file_name}"
                            break
                        
                        # handle special case where there are \r\n characters in the current chunk as this will cause search and replace to ALWAYS fail
                        carriage_return = False
                        if "\r\n" in current_chunk:
                            # replace in current chunk
                            previous_chunk = current_chunk
                            current_chunk = current_chunk.replace("\r\n", "\n")
                            carriage_return = True
                        # check to see that the original_code is in the new_code by trying all possible indentations
                        correct_indent, rstrip_original_code = manual_code_check(current_chunk, original_code)
                        # if the original_code couldn't be found in the chunk we need to let the llm know
                        if original_code not in current_chunk and correct_indent == -1:
                            chunks_with_original_code = [
                                index
                                for index, chunk in enumerate(file_chunks)
                                if original_code in chunk.replace("\r\n", "\n") or manual_code_check(chunk.replace("\r\n", "\n"), original_code)[0] != -1
                            ]
                            chunks_with_original_code = chunks_with_original_code[:5]

                            error_message = f"The original_code provided does not appear to be present in section {section_letter}. The original_code contains:\n```\n{original_code}\n```\nBut section {section_letter} in {file_name} has code:\n```\n{current_chunk}\n```"
                            if chunks_with_original_code:
                                error_message += "\n\nDid you mean one of the following sections?"
                                error_message += "\n".join(
                                    [
                                        f'\n<section id="{int_to_excel_col(index + 1)}">\n{file_chunks[index]}\n</section>\n```'
                                        for index in chunks_with_original_code
                                    ]
                                )
                            else:
                                # first check the lines in original_code, if it is too long, ask for smaller changes
                                original_code_lines_length = len(original_code.split("\n"))
                                if original_code_lines_length > 7:
                                    error_message += f"\n\nThe original_code seems to be quite long with {original_code_lines_length} lines of code. Break this large change up into a series of SMALLER changes to avoid errors like these! Try to make sure the original_code is under 7 lines. DOUBLE CHECK to make sure that this make_change tool call is only attempting a singular change, if it is not, make sure to split this make_change tool call into multiple smaller make_change tool calls!"
                                else:
                                    # generate the diff between the original code and the current chunk to help the llm identify what it messed up
                                    # chunk_original_code_diff = generate_diff(original_code, current_chunk) - not necessary
                                    error_message += f"\n\nIdentify what should be the correct original_code should be, and make another replacement with the corrected original_code. The original_code MUST be in section A in order for you to make a change. DOUBLE CHECK to make sure that this make_change tool call is only attempting a singular change, if it is not, make sure to split this make_change tool call into multiple smaller make_change tool calls!"
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
                        current_chunk_occurences = current_chunk.count(original_code)
                        if current_chunk_occurences > 1:
                            error_message = f"The original_code is not unique in the section {section_letter}. It appears {current_chunk_occurences} times! Make sure the original_code is unique in section {section_letter}!"
                            break

                        # apply changes
                        new_chunk = current_chunk.replace(original_code, new_code, 1)
                        if new_chunk == current_chunk:
                            logger.warning("No changes were made to the code.")
                        
                        file_chunks[section_id] = new_chunk
                        # if we had carriage returns, we need to update file_contents to remove them also from current_chunk
                        if carriage_return:
                            file_contents = file_contents.replace(previous_chunk, current_chunk, 1)
                        new_contents = file_contents.replace(
                            current_chunk, new_chunk, 1
                        )

                        # Check if changes were made
                        if new_contents == file_contents:
                            logger.warning("No changes were made to the code.")
                            error_message = "No changes were made, make sure original_code and new_code are not the same."
                            break
                        
                        # Check if the changes are valid
                        if not error_message:
                            check_results = get_check_results(file_name, new_contents) # the filename may be wrong here
                            # check_results_message = check_results.is_worse_than_message(initial_check_results) - currently unused
                            failing_parse = check_results.parse_error_message if not initial_check_results.parse_error_message else ""
                            current_diff = generate_diff(
                                file_contents, new_contents
                            )
                            if failing_parse:
                                error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code.\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the make_change tool with different changes that yield valid code."
                                break
                    if error_message:
                        logger.error(f"ERROR occured in make_change tool: {error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            error_message
                        )

                    if not error_message:
                        success_message = (
                            f"SUCCESS\n\nThe following changes have been applied to {file_name}:\n\n"
                            + generate_diff(file_contents, new_contents)
                        ) + f"{warning_message}\n\nYou can continue to make changes to the code sections and call the make_change tool again, or go back to searching for keywords using the search_codebase tool, which is great for finding all definitions or usages of a function or class."
                        # set contents
                        modify_files_dict[file_name]['contents'] = new_contents
                        modify_files_dict[file_name]['chunks'] = file_chunks
                        logger.info(success_message)

                        success_message = create_tool_call_response(tool_name, f"SUCCESS\n\n{success_message}")
                        
                        tool_name, tool_call = assistant_generator.send(
                            success_message
                        )
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
                            new_file_snippets = chunk_code(new_file_contents, new_full_file_path, 1400, 500)
                            new_file_contents_lines = new_file_contents.split("\n")
                            new_file_chunks = [
                                "\n".join(new_file_contents_lines[max(snippet.start - 1, 0) : snippet.end])
                                for snippet in new_file_snippets
                            ]
                            modify_files_dict[new_full_file_path] = {"chunks": new_file_chunks, "contents": new_file_contents, "original_contents": new_file_contents}
                            success_message = f"The new file {new_full_file_path} has been created successfully with the following contents:\n\n{new_file_contents}"
                    if error_message:
                        logger.debug(f"ERROR occured in create_file tool: {error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            error_message
                        )
                    else:
                        logger.debug(f"SUCCESS\n\n{success_message}")
                        success_message = create_tool_call_response(tool_name, f"SUCCESS\n\n{success_message}")
                        tool_name, tool_call = assistant_generator.send(
                            success_message
                        )
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
                            
                    # if no issues continue with search
                    if not error_message:
                        keyword = tool_call["keyword"].strip()
                        # search specific file
                        if file_name:
                            logger.info(f"Searching for keyword {keyword} in file {file_name}")
                            match_indices = []
                            match_context_indices = []
                            # if the current code file is not in the modify_files_dict, add it
                            if file_name not in modify_files_dict:
                                file_contents = read_file_with_fallback_encodings(full_file_path)
                                file_contents_lines = file_contents.split("\n")
                                original_file_snippets = chunk_code(file_contents, file_name, 1400, 500)
                                file_chunks = [
                                    "\n".join(file_contents_lines[max(snippet.start - 1, 0) : snippet.end])
                                    for snippet in original_file_snippets
                                ]
                                modify_files_dict[file_name] = {"chunks": copy.deepcopy(file_chunks), "contents": file_contents, "original_contents": file_contents}
                            # search current code file
                            file_chunks = modify_files_dict[file_name]["chunks"]
                            for i, chunk in enumerate(file_chunks):
                                if keyword in chunk:
                                    match_indices.append(i)
                                    match_context_indices.append(max(0, i - 1))
                                    match_context_indices.append(i)
                                    match_context_indices.append(min(len(file_chunks) - 1, i + 1))

                            match_indices = sorted(list(set(match_indices)))
                            match_context_indices = sorted(list(set(match_context_indices)))
                            if not match_indices:
                                logger.debug(f"The search term {keyword} does not appear to be present in the file: {file_name}. Consider missing or misplaced whitespace, comments or delimiters in the keyword.")
                                error_message = f"The search term {keyword} does not appear to be present in the file: {file_name}. Consider missing or misplaced whitespace, comments or delimiters in the keyword."
                            else:
                                # for matches inside current code file
                                sections_message = english_join(
                                    [
                                        int_to_excel_col(match_index + 1)
                                        for match_index in match_indices
                                    ]
                                )
                                starter_message = f"The keyword {keyword} was found in section(s) {sections_message} of {file_name}. They appear in the following places:\n\n"
                                success_message += (
                                    build_keyword_search_match_results(
                                        match_indices,
                                        file_chunks,
                                        keyword,
                                        starter_message,
                                        readonly=True
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
                                    rg_output_pretty = post_process_rg_output(cwd, sweep_config, output)
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
                                logger.debug(f"SUCCESS\n\nHere are the search_codebase results:\n{rg_output_pretty}\n\n")

                    if error_message:
                        logger.debug(f"ERROR in search_codebase\n\n{error_message}")
                        error_message = create_tool_call_response(tool_name, f"ERROR\n\n{error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            error_message
                        )
                    else:
                        logger.debug(success_message)
                        suffix = "\n\nMake additional search_codebase calls to find other keywords or start making changes by calling the make_change tool."
                        success_message = create_tool_call_response(tool_name, f"SUCCESS\n\n{success_message}{suffix}")
                        tool_name, tool_call = assistant_generator.send(
                            success_message
                        )
                else:
                    error_message = create_tool_call_response("UNKNOWN TOOL NAME", f"ERROR\nUnexpected tool name: {tool_name}")
                    tool_name, tool_call = assistant_generator.send(
                        error_message
                    )
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
            return modify_files_dict
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
        return None
    return None

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
