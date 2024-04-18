import copy
from math import inf
import os

from rapidfuzz import fuzz, process

from loguru import logger
from tqdm import tqdm
from sweepai.core.chat import ChatGPT, parse_function_calls_for_openai
from sweepai.core.entities import FileChangeRequest, Message
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.modify_utils import manual_code_check
from sweepai.utils.utils import get_check_results


modify_tools_openai = """
# make_change - Make a SINGLE, TARGETED code change in a file. Preserve whitespace, comments, and style. Changes should be minimal, self-contained, and address only one specific modification. If a change affects multiple separate code sections, use multiple calls to this tool, one for each section.
To call this tool you must respond in the following xml format:

<make_change>
<justification>
Explain how this SINGLE change contributes to fulfilling the user's request.
</justification>
<file_name>
Name of the file where the change will be made. Ensure correct spelling as this is case-sensitive.
</file_name>
<original_code>
The existing lines of code that need modification or replacement. This should be a SINGLE, CONTINUOUS block of code, not multiple separate sections. Include unchanged surrounding lines for context.
</original_code>
<new_code>
The new lines of code to replace the original code, implementing the SINGLE desired change. If the change is complex, break it into smaller targeted changes and use separate make_change calls for each.
</new_code>
</make_change>

# create_file - Create a new code file in the specified location with the given file name and extension. This is useful when the task requires adding entirely new functionality or classes to the codebase.
To call this tool you must respond in the following xml format:
<create_file>
<file_path>
The path where the new file should be created, relative to the root of the codebase. Do not include the file name itself.
</file_path>
<file_name>
he name to give the new file, including the extension. Ensure the name is clear, descriptive, and follows existing naming conventions.
</file_name>
<contents>
The initial contents of the new file.
</contents>
<justification>
Explain why creating this new file is necessary to complete the task and how it integrates with the existing codebase structure.
</justification>
</create_file>

# submit_result - Indicate that the task is complete and all requirements have been met. Provide the final code changes or solution.
To call this tool you must respond in the following xml format:
<submit_result>
<justification>
Summarize the code changes made and explain how they fulfill the user's original request. Provide the complete, modified code if applicable.
</justification>
</submit_result>"""

modify_tools = """<tool_description>
<tool_name>make_change</tool_name>
<description>
Make a SINGLE, TARGETED code change in a file. Preserve whitespace, comments, and style. Changes should be minimal, self-contained, and address only one specific modification. If a change affects multiple separate code sections, use this tool for one change at a time, one for each section.
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
The existing lines of code that need modification or replacement. This should be a short SINGLE, CONTINUOUS block of code, not multiple separate sections. Include unchanged surrounding lines for context.
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
<tool_name>submit_task</tool_name>
<description>
Indicate that the current task is complete.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Summarize the code changes made and explain how they fulfill the user's original request.
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

"""

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

<tool_description>
<tool_name>submit_task</tool_name>
<description>
Indicate that the current task is complete.
</description>
<parameters>
<parameter>
<name>justification</name>
<type>str</type>
<description>
Summarize the code changes made and explain how they fulfill the user's original request.
</description>
</parameter>
</parameters>
</tool_description>

If the current task is complete, call the submit_task function."""

NO_TOOL_CALL_PROMPT_OPENAI = """FAILURE
No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:

<function_call>
<tool_name>
<parameter1>
parameter1 value here
</parameter1>
<parameter2>
parameter2 value here
</parameter2>
</tool_name>
</function_call>

Here is an example:

<function_call>
<make_change>
<justification>
The justification for making this change goes here
</justification>
<file_name>
example-file.file
</file_name>
<original_code>
old code line here
</original_code>
<new_code>
new code line here
</new_code>
</make_change>
</function_call>

If the current task is complete, call the submit_task function.
"""

self_review_prompt = """First, review and critique the change(s) you have made. Consider the following points:

1. Analyze code patch and indicate:
   - Purpose and impact of each change
   - Check for potential errors: 
     - Logic errors
     - Unhandled edge cases
     - Missing imports
     - Incomplete changes
     - Undefined variables/functions
     - Usage of nullable attributes
     - Non-functional code
   - Alignment with plan and requirements
2. Perform critical contextual analysis:
   - Break down changes 
   - Explain reasoning
   - Identify logic issues, edge cases, plan deviations
   - Consider all scenarios and pitfalls
   - Consider backwards compatibility and future-proofing
   - Suggest fixes for problems
3. Be extremely critical. Do not overlook ANY issues.

Limit the scope of the critique to the current task, which is:

{current_task}

Then, determine if the changes are correct and complete.

If the changes are complete and correct, call the submit_task function to move onto the next task. Otherwise, call make_changes to continue making changes."""

tool_call_parameters = {
    "make_change": ["justification", "file_name", "original_code", "new_code"],
    "create_file": ["justification", "file_name", "file_path", "contents"],
    "submit_task": ["justification"],
}

def english_join(items: list[str]) -> str:
    if len(items) == 0:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"

def find_best_match(needle: str, haystack: str, threshold: int = 80):
    best_match = 0
    best_score = 0
    threshold = 80
    file_contents_lines = haystack.split("\n")
    num_lines = len(file_contents_lines)
    num_match_lines = len(needle.split("\n"))
    for start_line in tqdm(range(num_lines), total=num_lines):
        potential_choices = []
        for end_line in range(start_line + max(1, num_match_lines - 5), start_line + num_match_lines + 5):
            if end_line > num_lines:
                break
            potential_choice = "\n".join(file_contents_lines[start_line:end_line])
            potential_choices.append(potential_choice)

        results = process.extractOne(needle, potential_choices, scorer=fuzz.QRatio, score_cutoff=threshold)
            
        if results is not None:
            choice, score, _index = results

            if score > best_score:
                best_score = score
                best_match = choice
    
    if best_score > threshold:
        return best_match, best_score
    return "", 0

MODEL = "claude-3-opus-20240229"

def validate_and_parse_function_call_openai(
    function_calls_string: str, chat_gpt: ChatGPT
) -> list[AnthropicFunctionCall]:
    function_calls = parse_function_calls_for_openai(
        function_calls_string.strip("\n") + "\n</function_call>"
    )
    if len(function_calls) > 0:
        function_calls[0] = AnthropicFunctionCall(
            function_name=function_calls[0]['tool'],
            function_parameters=function_calls[0]['arguments'],
        )
        if "<function_call>" in function_calls_string:
            chat_gpt.messages[-1].content = (
                chat_gpt.messages[-1].content.rstrip("\n") + "\n</function_call>"
            )
    return function_calls[0] if len(function_calls) > 0 else None


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

def create_user_message(
        fcrs: list[FileChangeRequest],
        request: str,
        cloned_repo: ClonedRepo,
        relevant_filepaths: list[str] = None,
        modify_files_dict: dict[str, dict[str, str]] = None
    ) -> str:
    current_fcr_index = 0
    for current_fcr_index, fcr in enumerate(fcrs):
        if not fcr.is_completed:
            break
    combined_request_unformatted = "{relevant_files}# Plan of Code Changes\n\nIn order to solve the user's request you will need to modify or create {files_to_modify_list}.{completed_prompt} Here are the instructions for the edits you need to make:\n\n<files_to_change>\n{files_to_modify}\n</files_to_change>"
    completed_prompt = "" if current_fcr_index == 0 else f" You have already completed {current_fcr_index} of the {len(fcrs)} required changes."
    if modify_files_dict:
        combined_request_unformatted += "\nThe above files reflect the latest updates you have already made. READ THROUGH THEM CAREFULLY TO FIGURE OUT WHAT YOUR NEXT STEPS ARE. Call the make_change, create_file or submit_task tools."
    files_to_modify_string = ""

    files_to_modify_messages = {fcr.filename: "" for fcr in fcrs}
    for i, fcr in enumerate(fcrs):
        # first add the instructions to the user message
        if i < current_fcr_index: # already done
            files_to_modify_messages[fcr.filename] += f"\n\nYou have already {fcr.change_type} {fcr.filename}, where the specific instructions were to:\n\n{fcr.instructions}"
        elif i == current_fcr_index:
            files_to_modify_messages[fcr.filename] += f"\n\nYour current task is to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
        else:
            files_to_modify_messages[fcr.filename] += f"\n\nYou will later need to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
        # now add the contents of the file to the user message
        # only add the contents if this is the last fcr for the filename
        last_occurence = i
        # loop from current index to end of fcrs to see if this fcr is the last time the filename shows up
        for j in range(i + 1, len(fcrs)):
            if fcrs[j].filename == fcr.filename:
                last_occurence = j
        if last_occurence == i:
            if fcr.change_type == "modify":
                if not modify_files_dict:
                    files_to_modify_messages[fcr.filename] += f"\n\n<file_to_modify filename=\"{fcr.filename}\">\n{cloned_repo.get_file_contents(file_path=fcr.filename)}\n</file_to_modify>"
                else: # show the latest contents of the file
                    latest_file_contents = get_latest_contents(fcr.filename, cloned_repo, modify_files_dict)
                    files_to_modify_messages[fcr.filename] += f"\n\n<file_to_modify filename=\"{fcr.filename}\">\n{latest_file_contents}\n</file_to_modify>"
            elif fcr.change_type == "create":
                files_to_modify_messages[fcr.filename] += f"\n<file_to_create filename=\"{fcr.filename}\">\n{fcr.instructions}\n</file_to_create>"
    # now we combine the messages into a single string
    already_added_files = set([])
    for fcr in fcrs:
        if fcr.filename in already_added_files:
            continue
        files_to_modify_string += files_to_modify_messages[fcr.filename]
        already_added_files.add(fcr.filename)

    deduped_file_names = []
    for fcr in fcrs:
        if fcr.filename not in deduped_file_names:
            deduped_file_names.append(fcr.filename)
    combined_request_message = combined_request_unformatted \
        .replace("{files_to_modify}", files_to_modify_string.lstrip('\n')) \
        .replace("{files_to_modify_list}", english_join(deduped_file_names)) \
        .replace("{completed_prompt}", completed_prompt)
    if relevant_filepaths:
        relevant_file_paths_string = ""
        for relevant_file_path in relevant_filepaths:
            if relevant_file_path not in cloned_repo.get_file_list():
                logger.warning(f"Relevant file path {relevant_file_path} not found in cloned repo.")
                continue
            if relevant_file_path in [fcr.filename for fcr in fcrs]:
                logger.warning(f"Relevant file path {relevant_file_path} is already in the list of files to modify.")
                continue
            relevant_file_paths_string += f"\n\n<relevant_module filename=\"{relevant_file_path}\">\n{cloned_repo.get_file_contents(file_path=relevant_file_path)}\n</relevant_module>"
        relevant_file_paths_string = f"<relevant_files>\n{relevant_file_paths_string}\n</relevant_files>"
        combined_request_message.replace("{relevant_files}", f'\nHere are some relevant modules, such as useful helper functions for resolving this issue. You likely will not need to edit these modules but may need to import them or understand their usage interface: {relevant_file_paths_string}\n')
    else:
        combined_request_message.replace("{relevant_files}", "")
    user_message = f"<user_request>\n{request}\n</user_request>\n{combined_request_message}"
    return user_message

# find out if any changes were made by matching the contents of the files
def changes_made(modify_files_dict: dict[str, dict[str, str]], previous_modify_files_dict) -> bool:
    # check if there are any changes made
    for file_name, file_data in modify_files_dict.items():
        if file_name not in previous_modify_files_dict:
            if file_data['contents'] != file_data["original_contents"]:
                return True
            else:
                continue
        if file_data['contents'] != previous_modify_files_dict[file_name]['contents']:
            return True
    return False

past_tense_mapping = {
    "modify": "modified",
    "create": "created",
}

# Magic
def ordinal(n: int):
    return "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4]) # noqa

def render_plan(fcrs: list[FileChangeRequest]) -> str:
    current_fcr_index = 0
    for current_fcr_index, fcr in enumerate(fcrs):
        if not fcr.is_completed:
            break
    plan = f"You have {len(fcrs)} changes to make and you are currently working on the {ordinal(current_fcr_index + 1)} task."
    for i, fcr in enumerate(fcrs):
        if i < current_fcr_index:
            plan += f"\n\nTask {i}: You have previously {past_tense_mapping[fcr.change_type]} {fcr.filename}, where you were asked to:\n\n{fcr.instructions}"
        elif i == current_fcr_index:
            plan += f"\n\nTask {i}: Your CURRENT TASK is to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
        else:
            plan += f"\n\nTask {i}: You will later need to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n{fcr.instructions}"
    return plan.strip('\n')

def render_current_task(fcrs: list[FileChangeRequest]) -> str:
    current_fcr_index = 0
    for current_fcr_index, fcr in enumerate(fcrs):
        if not fcr.is_completed:
            break
    fcr = fcrs[current_fcr_index]
    return f"The CURRENT TASK is to {fcr.change_type} {fcr.filename}. The specific instructions to do so are listed below:\n\n<current_task>\n{fcr.instructions}\n</current_task>"

def modify(
    fcrs: list[FileChangeRequest],
    request: str,
    cloned_repo: ClonedRepo,
    relevant_filepaths: list[str],
    chat_logger: ChatLogger | None = None,
    use_openai: bool = False,
) -> dict[str, dict[str, str]]:
    # join fcr in case of duplicates
    user_message = create_user_message(
        fcrs=fcrs,
        request=request,
        cloned_repo=cloned_repo,
        relevant_filepaths=relevant_filepaths,
    )
    chat_gpt = ChatGPT()
    full_instructions = instructions + (modify_tools_openai if use_openai else modify_tools)
    chat_gpt.messages = [Message(role="system", content=full_instructions)]
    try:
        function_calls_string = chat_gpt.chat_anthropic(
            content=f"Here is the intial user request, plan, and state of the code files:\n{user_message}",
            stop_sequences=["</function_call>"],
            model=MODEL,
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
    modify_files_dict = {}
    llm_state = {
        "initial_check_results": {},
        "done_counter": 0,
        "request": request,
        "plan": render_plan(fcrs), 
        "current_task": render_current_task(fcrs),
        "user_message_index": 1,
        "user_message_index_chat_logger": 1,
        "fcrs": fcrs,
        "previous_attempt": "",
    }
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
            # note that detailed_chat_logger_messages is meant to be modified in place by handle_function_call
            function_output, modify_files_dict, llm_state = handle_function_call(cloned_repo, function_call, modify_files_dict, llm_state, chat_logger_messages=detailed_chat_logger_messages, use_openai=use_openai)
            if function_output == "DONE":
                # add the diff of all changes to chat_logger
                if chat_logger:
                    final_message = "DONE\nHere is a summary of all the files changed:\n\n"
                    for file_name, file_data in modify_files_dict.items():
                        file_diff = generate_diff(file_data['original_contents'], file_data['contents'])
                        if file_diff:
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
                
                # update context if a change was made
                if changes_made(modify_files_dict, previous_modify_files_dict):
                    # remove the previous user message and add it to the end, do not remove if it is the inital user message
                    if llm_state["user_message_index"] != 1:
                        chat_gpt.messages.pop(llm_state["user_message_index"])
                    if llm_state["user_message_index_chat_logger"] != 1:
                        detailed_chat_logger_messages.pop(llm_state["user_message_index_chat_logger"])
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
            function_calls_string = chat_gpt.chat_anthropic(
                content=function_output,
                model=MODEL,
                stop_sequences=["</function_call>"],
                use_openai=use_openai,
            )
            detailed_chat_logger_messages.append({"role": "assistant", "content": function_calls_string})
        except Exception as e:
            logger.error(f"Error in chat_anthropic: {e}")
            chat_logger.add_chat(
                {
                    "model": chat_gpt.model,
                    "messages": detailed_chat_logger_messages,
                    "output": f"ERROR: AN ERROR OCCURED ON ITERATION {i + 1}:\n{e}\nEND OF ERROR",
                })
            break
    # before we return clean up modify files dict by removing any files with no changes
    files_to_remove = []
    for file_name, file_data in modify_files_dict.items():
        if not file_data or file_data['original_contents'] == file_data['contents']:
            files_to_remove.append(file_name)
    for file_name in files_to_remove:
        modify_files_dict.pop(file_name)
        logger.info(f"Removed file {file_name} from modify_files_dict as it had no changes.")
    return modify_files_dict


def generate_diffs(modify_files_dict: dict[str, dict[str, str]]) -> dict[str, str]:
    changes_made = False
    for file_name, file_data in modify_files_dict.items():
        new_contents = file_data["contents"]
        original_contents = file_data["original_contents"]
        diff = generate_diff(original_contents, new_contents)
        if diff:
            changes_made = True
    return changes_made

def create_tool_call_response(tool_name: str, tool_call_response_contents: str) -> str:
    return f"<function_results>\n<result>\n<tool_name>{tool_name}<tool_name>\n<stdout>\n{tool_call_response_contents}\n</stdout>\n</result>\n</function_results>"

def get_latest_contents(file_name: str, cloned_repo: ClonedRepo, modify_files_dict: dict) -> str:
    if file_name in modify_files_dict and "contents" in modify_files_dict[file_name]:
        return modify_files_dict[file_name]["contents"]
    elif file_name in cloned_repo.get_file_list():
        return cloned_repo.get_file_contents(file_name)
    else:
        return ""

def handle_function_call(
    cloned_repo: ClonedRepo,
    function_call: AnthropicFunctionCall,
    modify_files_dict: dict[str, dict[str, str]],
    llm_state: dict,
    chat_logger_messages: list[dict[str, str]] | None = None,
    use_openai: bool = False,
) :
    # iterate through modify_files_dict and generate diffs
    llm_response = ""
    tool_name = function_call.function_name
    tool_call = function_call.function_parameters
    if tool_name == "submit_task":
        changes_made = generate_diffs(modify_files_dict)
        if changes_made:
            llm_response = "DONE"
        else:
            llm_state["done_counter"] += 1
            if llm_state["done_counter"] > 3:
                llm_response = "DONE"
            else:
                llm_response = "ERROR\n\nNo changes were made. Please continue working on your task."

        for fcr in llm_state["fcrs"]:
            if not fcr.is_completed:
                fcr.is_completed = True
                llm_response = f"SUCCESS\n\nThe current task is complete. Please move on to the next task. {llm_state['current_task']}"
                break

        if all([fcr.is_completed for fcr in llm_state["fcrs"]]):
            llm_response = "DONE"
    elif tool_name == "no_tool_call":
        if use_openai:
            llm_response = NO_TOOL_CALL_PROMPT_OPENAI
        else:
            llm_response = NO_TOOL_CALL_PROMPT
    elif tool_name == "make_change":
        error_message = ""
        for key in ["file_name", "original_code", "new_code"]:
            if key not in tool_call:
                error_message += f"Missing {key} in tool call. Call the tool again but this time provide the {key}.\n"
                if key == "new_code" or key == "original_code":
                    error_message += "\n\nIt is likely the reason why you have missed these keys is because the original_code block you provided is WAY TOO LARGE and as such you have missed the closing xml tags. REDUCE the original_code block to be under 10 lines of code!"
        warning_message = ""
        if not error_message:
            for _ in range(1): # this is super jank code but it works for now - only for easier error message handling
                # ensure the file we are editting exists and is in modify_files_dict
                if "file_name" in tool_call:
                    file_name = tool_call["file_name"].strip()
                    # if not in codebase or has not been created
                    if not os.path.exists(os.path.join(cloned_repo.repo_dir, file_name)) and file_name not in modify_files_dict:
                        error_message += f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!\n"
                        break
                llm_state['initial_check_results'][file_name] = get_check_results(file_name, get_latest_contents(file_name, cloned_repo, modify_files_dict))
                success_message = ""
                original_code = tool_call["original_code"].strip("\n")
                new_code = tool_call["new_code"].strip("\n")
                if new_code == original_code:
                    error_message += "The new_code and original_code are the same. Are you CERTAIN this change needs to be made? If you are certain this change needs to be made, MAKE SURE that the new_code and original_code are NOT the same."
                    break
                if not original_code:
                    error_message = "The original_code is empty. Make sure that the original_code is not empty and that it is a valid section of code that you are trying to replace."
                # get the latest contents of the file
                file_contents = get_latest_contents(file_name, cloned_repo, modify_files_dict)
                # if the file is not in modify_files_dict, add it
                if file_name not in modify_files_dict:
                    modify_files_dict[file_name] = {"contents": file_contents, "original_contents": file_contents}
                warning_message = ""
                
                # handle special case where there are \r\n characters in the current chunk as this will cause search and replace to ALWAYS fail
                if "\r\n" in file_contents:
                    # replace in current chunk
                    file_contents = file_contents.replace("\r\n", "\n")
                # check to see that the original_code is in the new_code by trying all possible indentations
                correct_indent, rstrip_original_code = manual_code_check(file_contents, original_code)
                # if the original_code couldn't be found in the chunk we need to let the llm know
                if original_code not in file_contents and correct_indent == -1:
                    # TODO: add weighted ratio to the choices, penalize whitespace less
                    best_match, best_score = find_best_match(original_code, file_contents)

                    if best_score > 80:
                        error_message = f"The original_code provided does not appear to be present in file {file_name}. The original_code contains:\n```\n{tool_call['original_code']}\n```\nDid you mean the following?\n```\n{best_match}\n```\nHere is the diff:\n```\n{generate_diff(tool_call['original_code'], best_match)}\n```"
                    else:
                        error_message = f"The original_code provided does not appear to be present in file {file_name}. The original_code contains:\n```\n{tool_call['original_code']}\n```\nBut this section of code was not found anywhere inside the current file. DOUBLE CHECK that the change you are trying to make is not already implemented in the code!"
                    
                    # first check the lines in original_code, if it is too long, ask for smaller changes
                    original_code_lines_length = len(original_code.split("\n"))
                    if original_code_lines_length > 10:
                        error_message += f"\n\nThe original_code seems to be quite long with {original_code_lines_length} lines of code. Break this large change up into a series of SMALLER changes to avoid errors like these! Try to make sure the original_code is under 10 lines. DOUBLE CHECK to make sure that this make_change tool call is only attempting a singular change, if it is not, make sure to split this make_change tool call into multiple smaller make_change tool calls!"
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
                    if current_chunk_occurences * len(original_code.split("\n")) < 50:
                        # We start by setting original_code_lines with indentation fixed. Sometimes the model forgets to indent the first line.

                        # INDENTATION FIX START #
                        start_line = -1
                        min_diff = inf
                        file_contents_lines = file_contents.split("\n")
                        for index, _line in enumerate(file_contents_lines):
                            if all(original_line.lstrip() == file_contents_line.lstrip() for original_line, file_contents_line in zip(original_code_lines, file_contents_lines[index:index + len(original_code_lines)])):
                                # if abs(len(line) - len(first_line)) < min_diff:
                                current_diff = sum(abs(len(original_line) - len(file_contents_line)) for original_line, file_contents_line in zip(original_code_lines, file_contents_lines[index:index + len(original_code_lines)]))
                                if current_diff < min_diff:
                                    min_diff = current_diff
                                    start_line = index
                                    if min_diff == 0:
                                        break

                        if start_line == -1:
                            error_message = f"The original_code is not unique to the file `{file_name}`. It appears {current_chunk_occurences} times in the file. For the `original_code` to be valid, it must be unique within the file.\n\nTo resolve this issue, please provide a unique `original_code` by including some surrounding lines for context. Make sure the selected code snippet appears only once in the file."
                            break
                            
                        original_code_lines = file_contents_lines[start_line:start_line + len(original_code_lines)]
                        # INDENTATION FIX END #

                        # Then we find all the matches and their surrounding lines.
                        matches = []
                        surrounding_lines = 5

                        for i in range(len(file_contents_lines)):
                            if "\n".join(original_code_lines) == "\n".join(file_contents_lines[i:i + len(original_code_lines)]):
                                match_ = "\n".join(file_contents_lines[max(0, i - surrounding_lines):i])
                                match_ += "\n" + "===== START =====" + "\n"
                                match_ += "\n".join(file_contents_lines[i:i + len(original_code_lines)])
                                match_ += "\n" + "===== END =====" + "\n"
                                match_ += "\n".join(file_contents_lines[i + len(original_code_lines):i + len(original_code_lines) + surrounding_lines])
                                matches.append(match_)

                        error_message = f"The original_code is not unique to the file `{file_name}`. It appears {current_chunk_occurences} times in the file. For the `original_code` to be valid, it must be unique within the file.\n\nTo resolve this issue, please provide a unique `original_code` by including some surrounding lines for context. Make sure the selected code snippet appears only once in the file. Here are the {current_chunk_occurences} occurences of the `original_code` in the file with their surrounding lines:\n\n" + "\n\n".join([f"Occurrence {i + 1}:\n```\n{match_}\n```" for i, match_ in enumerate(matches)]) + "\n\nPlease provide a unique `original_code` by selecting one of these occurrences and including additional context if necessary."
                    else:
                        error_message = f"The original_code is not unique to the file `{file_name}`. It appears {current_chunk_occurences} times in the file. For the `original_code` to be valid, it must be unique within the file.\n\nTo resolve this issue, please provide a unique `original_code` by including some surrounding lines for context. Make sure the selected code snippet appears only once in the file."
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
                    check_results_message = check_results.is_worse_than_message(llm_state['initial_check_results'][file_name])
                    failing_parse = check_results.parse_error_message if not llm_state['initial_check_results'][file_name].parse_error_message else ""
                    current_diff = generate_diff(
                        file_contents, new_file_contents
                    )
                    if failing_parse:
                        error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code with the following error logs:\n```\n{failing_parse}\n```\n\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the make_change tool with different changes that yield valid code."
                        break
                    elif check_results_message:
                        warning_message = check_results_message
        if error_message:
            llm_response = f"ERROR\n\n{error_message}"
        if not error_message:
            success_message = (
                f"SUCCESS\n\nThe following changes have been applied to {file_name}:\n\n"
                + generate_diff(file_contents, new_file_contents)
            ) + f"{warning_message}\n\nYou can continue to make changes to the file {file_name} and call the make_change tool again, or handle the rest of the plan. REMEMBER to add all necessary imports at the top of the file, if the import is not already there!"
            # set contents
            if file_name not in modify_files_dict:
                modify_files_dict[file_name] = {
                    "contents": file_contents,
                    "original_contents": file_contents,
                }
            if warning_message:
                llm_response = f"SUCCESS\n\nThe following changes have been applied:\n\n```diff\n{generate_diff(file_contents, new_file_contents)}\n```\nThe code changes also yield the following warnings:\n```\n{warning_message}\n```\n\n{self_review_prompt.format(current_task=llm_state['current_task'])}"
            else:
                llm_response = f"SUCCESS\n\nThe following changes have been applied:\n\n```diff\n{generate_diff(file_contents, new_file_contents)}\n```\n{self_review_prompt.format(current_task=llm_state['current_task'])}"
            modify_files_dict[file_name]['contents'] = new_file_contents
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
                error_message = f"The directory {os.path.dirname(new_full_file_path)} does not exist. Make sure the new file you want to create exists within an existing directory!"
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