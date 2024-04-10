

import os

from loguru import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Message
from sweepai.core.reflection_utils import ModifyEvaluatorAgent
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.modify_utils import manual_code_check
from sweepai.utils.utils import get_check_results

TOTAL_MODIFY_ITERATIONS = 10

modify_tools = """<tool_description>
<tool_name>make_change</tool_name>
<description>
Make a SINGLE, TARGETED code change in a file. Preserve whitespace, comments, and style. Changes should be minimal, self-contained, and address only one specific modification. If a change affects multiple separate code sections, use multiple calls to this tool, one for each section.
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
Name of the file where the change will be made. Ensure correct spelling as this is case-sensitive.
</description>
</parameter>
<parameter>
<name>original_code</name>
<type>str</type>
<description>
The existing lines of code that need modification or replacement. This should be a SINGLE, CONTINUOUS block of code, not multiple separate sections. Include unchanged surrounding lines for context.
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
<name>contents</name>
<type>str</type>
<description>
The initial contents of the new file.
</description>
</parameter>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Explain why creating this new file is necessary to complete the task and how it integrates with the existing codebase structure.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>submit_result</tool_name>
<description>
Indicate that the task is complete and all requirements have been met. Provide the final code changes or solution.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Summarize the code changes made and explain how they fulfill the user's original request. Provide the complete, modified code if applicable.
</description>
</parameter>
</parameters>
</tool_description>"""

instructions = """You are an expert software developer tasked with editing code to fulfill the user's request. Your goal is to make the necessary changes to the codebase while following best practices and respecting existing conventions. 

To complete the task, follow these steps:

1. If new functionality is required that doesn't fit into existing files, create a new file with an appropriate name and location.

2. Make the code changes in a targeted way:
    - Preserve existing whitespace, comments and code style
    - Make surgical edits to only the required lines of code
    - If a change is complex, break it into smaller incremental changes
    - Ensure each change is complete and functional before moving on
        When providing code snippets, be extremely precise with indentation:
        - Count the exact number of spaces used for indentation
        - If tabs are used, specify that explicitly 
        - Ensure the indentation of the code snippet matches the original file exactly
3. After making all the changes, review the modified code to verify it fully satisfies the original request.
4. Once you are confident the task is complete, submit the final solution.

In this environment, you have access to the following tools to assist in fulfilling the user request:

You MUST call them like this:
<function_call>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_call>

Here are the tools available:

""" + modify_tools

NO_TOOL_CALL_PROMPT = """FAILURE
No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:

<function_call>
<invoke>
<tool_name>tool_name</tool_name>
<parameters>
<param_name>param_value</param_name>
</parameters>
</invoke>
</function_call>

Here is an example:

<function_call>
<invoke>
<tool_name>analyze_problem_and_propose_plan</tool_name>
<parameters>
<problem_analysis>The problem analysis goes here</problem_analysis>
<proposed_plan>The proposed plan goes here</proposed_plan>
</parameters>
</invoke>
</function_call>

If you are really done, call the submit_result function.
"""

tool_call_parameters = {
    "analyze_problem_and_propose_plan": ["problem_analysis", "proposed_plan"],
    "search_codebase": ["justification", "file_name", "keyword"],
    "analyze_and_identify_changes": ["file_name", "changes"],
    "view_file": ["justification", "file_name"],
    "make_change": ["justification", "file_name", "original_code", "new_code"],
    "get_code_snippet_to_change": ["justification", "file_name", "start_line", "end_line"],
    "create_file": ["justification", "file_name", "file_path", "contents"],
    "submit_result": ["justification"],
}

MODEL = "claude-3-opus-20240229"

def validate_and_parse_function_call(
    function_calls_string: str, chat_gpt: ChatGPT
) -> list[AnthropicFunctionCall]:
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</function_call>"
    )  # add end tag
    if len(function_calls) > 0:
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</function_call>"
        )  # add end tag to assistant message
        return function_calls[0] if len(function_calls) > 0 else None

    # try adding </invoke> tag as well
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</invoke>\n</function_call>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</invoke>\n</function_call>"
        )
        return function_calls[0] if len(function_calls) > 0 else None
    # try adding </parameters> tag as well
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n")
        + "\n</parameters>\n</invoke>\n</function_call>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n")
            + "\n</parameters>\n</invoke>\n</function_call>"
        )
    return function_calls[0] if len(function_calls) > 0 else None

def modify(
        fcrs: list[FileChangeRequest],
        request: str,
        cloned_repo: ClonedRepo,
        relevant_filepaths: list[str],
    ) -> dict[str, dict[str, str]]:
    combined_request_unformatted = "In order to solve the user's request you will need to modify/create the following files:\n\n{files_to_modify}\n\nThe order you choose to modify/create these files is up to you.\n"
    files_to_modify = ""
    for fcr in fcrs:
        files_to_modify += f"\n\nYou will need to {fcr.change_type} {fcr.filename}, the specific instructions to do so are listed below:\n\n{fcr.instructions}"
        if fcr.change_type == "modify":
            files_to_modify += f"\n<file_to_modify filename=\"{fcr.filename}\">\n{cloned_repo.get_file_contents(file_path=fcr.filename)}\n</file_to_modify>"
        elif fcr.change_type == "create":
            files_to_modify += f"\n<file_to_create filename=\"{fcr.filename}\">\n{fcr.instructions}\n</file_to_create>"
    
    combined_request_message = combined_request_unformatted.replace("{files_to_modify}", files_to_modify.lstrip('\n'))
    if relevant_filepaths:
        relevant_file_paths_string = ""
        for relevant_file_path in relevant_filepaths:
            if relevant_file_path not in cloned_repo.get_file_list():
                logger.warning(f"Relevant file path {relevant_file_path} not found in cloned repo.")
                continue
            relevant_file_paths_string += f"\n\n<relevant_file filename=\"{relevant_file_path}\">\n{cloned_repo.get_file_contents(file_path=relevant_file_path)}\n</relevant_file>"
        combined_request_message += f'\nYou should view the following relevant files: {relevant_file_paths_string}\n\nREMEMBER YOUR END GOAL IS TO SATISFY THE # User Request'
    user_message = f"# User Request\n{request}\n{combined_request_message}"
    chat_gpt = ChatGPT()
    chat_gpt.messages = [Message(role="system", content=instructions)]
    function_calls_string = chat_gpt.chat_anthropic(
        content=user_message,
        stop_sequences=["</function_call>"],
        model=MODEL,
        message_key="user_request",
    )
    modify_files_dict = {}
    llm_state = {
        "initial_check_results": {},
        "done_counter": 0,
        "request": request,
        "plan": "\n".join(f"<instructions file_name={fcr.filename}>\n{fcr.instructions}\n</instructions>" for fcr in fcrs)
    }
    for _ in range(TOTAL_MODIFY_ITERATIONS):
        function_call = validate_and_parse_function_call(function_calls_string, chat_gpt)
        if function_call:
            function_output, modify_files_dict, llm_state = handle_function_call(cloned_repo, function_call, modify_files_dict, llm_state)
        else:
            function_output = "FAILURE: No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n" \
                + "<function_call>\n<invoke>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</invoke>\n</function_call>"
        try:
            function_calls_string = chat_gpt.chat_anthropic(
                content=function_output,
                model=MODEL,
                stop_sequences=["</function_call>"],
            )
        except Exception as e:
            logger.error(f"Error in chat_anthropic: {e}")
            break
    return modify_files_dict


def generate_diffs(modify_files_dict: dict[str, dict[str, str]]) -> dict[str, str]:
    for file_name, file_data in modify_files_dict.items():
        new_contents = file_data["contents"]
        original_contents = file_data["original_contents"]
        diff = generate_diff(original_contents, new_contents)
        if diff:
            changes_made = True
    return changes_made

def create_tool_call_response(tool_name: str, tool_call_response_contents: str) -> str:
    return f"<function_results>\n<result>\n<tool_name>{tool_name}<tool_name>\n<stdout>\n{tool_call_response_contents}\n</stdout>\n</result>\n</function_results>"

def handle_function_call(
        cloned_repo: ClonedRepo,
        function_call: AnthropicFunctionCall,
        modify_files_dict: dict[str, dict[str, str]],
        llm_state: dict,
    ) :
    # iterate through modify_files_dict and generate diffs
    llm_response = ""
    tool_name = function_call.function_name
    tool_call = function_call.function_parameters
    if tool_name == "submit_result":
        changes_made = False
        changes_made = generate_diffs(modify_files_dict)
        if changes_made:
            llm_response = "DONE"
        else:
            llm_state["done_counter"] += 1
            if llm_state["done_counter"] > 3:
                llm_response = "DONE"
            else:
                llm_response = "ERROR\n\nNo changes were made. Please continue working on your task."
    elif tool_name == "no_tool_call":
        llm_response = NO_TOOL_CALL_PROMPT
    elif tool_name == "make_change":
        error_message = ""
        for key in ["file_name", "original_code", "new_code"]:
            if key not in tool_call:
                error_message += f"Missing {key} in tool call.Call the tool again but this time provide the {key}.\n"
                if key == "new_code" or key == "original_code":
                    error_message += "\n\nIt is likely the reason why you have missed these keys is because the original_code you provided is WAY TOO LARGE and as such you have missed the closing xml tags. REDUCE the original_code block to be under 10 lines of code!"
        for _ in range(1): # this is super jank code but it works for now - only for easier error message handling
            # ensure the file we are editting exists and is in modify_files_dict
            if "file_name" in tool_call:
                file_name = tool_call["file_name"].strip()
                # if not in codebase or has not been created
                if not os.path.exists(os.path.join(cloned_repo.repo_dir, file_name)) and file_name not in modify_files_dict:
                    error_message += f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!\n"
                    break
            def get_latest_contents(file_name) -> str:
                if file_name in modify_files_dict:
                    return modify_files_dict[file_name]["contents"]
                elif file_name in cloned_repo.get_file_list():
                    return cloned_repo.get_file_contents(file_name)
                else:
                    return ""
            llm_state['initial_check_results'][file_name] = get_check_results(file_name, get_latest_contents(file_name))
            success_message = ""
            original_code = tool_call["original_code"].strip("\n")
            new_code = tool_call["new_code"].strip("\n")
            if new_code == original_code:
                error_message += "The new_code and original_code are the same. Are you CERTAIN this change needs to be made? If you are certain this change needs to be made, MAKE SURE that the new_code and original_code are NOT the same."
                break
            # get the latest contents of the file
            file_contents = get_latest_contents(file_name)
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
                failing_parse = check_results.parse_error_message if not llm_state['initial_check_results'][file_name].parse_error_message else ""
                current_diff = generate_diff(
                    file_contents, new_file_contents
                )
                if failing_parse:
                    error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code with the following error logs:\n{failing_parse}\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the make_change tool with different changes that yield valid code."
                    break
        if error_message:
            llm_response = f"ERROR\n\n{error_message}"
        if not error_message:
            success_message = (
                f"SUCCESS\n\nThe following changes have been applied to {file_name}:\n\n"
                + generate_diff(file_contents, new_file_contents)
            ) + f"{warning_message}\n\nYou can continue to make changes to the file {file_name} and call the make_change tool again, or go back to searching for keywords using the search_codebase tool, which is great for finding all definitions or usages of a function or class. REMEMBER to add all necessary imports at the top of the file, if the import is not already there!"
            # set contents
            if file_name not in modify_files_dict:
                modify_files_dict[file_name] = {}
            overall_score, message_to_contractor = ModifyEvaluatorAgent().evaluate_patch(
                problem_statement=llm_state["request"],
                patch = generate_diff(file_contents, new_file_contents),
                changed_files=modify_files_dict,
                current_plan=llm_state["plan"],
                file_name=file_name,
            )
            if overall_score >= 8:
                llm_response = f"SUCCESS\n\n{success_message}"
                modify_files_dict[file_name]["original_contents"] = file_contents
                modify_files_dict[file_name]['contents'] = new_file_contents
            elif overall_score >= 3:
                # guard modify files
                llm_response = f"Changes Applied with FEEDBACK:\n\n{message_to_contractor}"
                modify_files_dict[file_name]["original_contents"] = file_contents
                modify_files_dict[file_name]['contents'] = new_file_contents
            else:
                llm_response = f"Changes Rejected with ERROR:\n\n{message_to_contractor}"
    elif tool_name == "create_file":
        error_message = ""
        success_message = ""
        for key in tool_call_parameters[tool_name]:
            if key not in tool_call:
                error_message += f"No {key} was provided in the {tool_name} tool call. Call the tool again but this time provide the {key}.\n"
        if not error_message:
            new_file_path = tool_call["file_path"].strip()
            new_file_name = tool_call["file_name"].strip()
            new_file_contents = tool_call["contents"].strip()
            new_file_dir = os.path.join(cloned_repo.repo_dir, new_file_path)
            new_full_file_path = os.path.join(new_file_path, new_file_name)
            new_full_file_path_with_cwd = os.path.join(cloned_repo.repo_dir, new_file_path, new_file_name)
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
            llm_response = f"ERROR\n\n{error_message}"
        else:
            llm_response = f"SUCCESS\n\n{success_message}"
    else:
        llm_response = f"ERROR\nUnexpected tool name: {tool_name}"
    return llm_response, modify_files_dict, llm_state

if __name__ == "__main__":
    pass