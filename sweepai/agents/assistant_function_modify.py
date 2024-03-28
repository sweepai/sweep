from copy import deepcopy
import copy
import os
import json
import subprocess
import traceback
from collections import defaultdict

from loguru import logger

from sweepai.agents.assistant_wrapper import openai_assistant_call
from sweepai.agents.agent_utils import ensure_additional_messages_length
from sweepai.config.client import SweepConfig
from sweepai.core.entities import AssistantRaisedException, FileChangeRequest, Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.diff import generate_diff
from sweepai.utils.file_utils import read_file_with_fallback_encodings
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.utils import chunk_code, get_check_results
from sweepai.utils.modify_utils import post_process_rg_output, manual_code_check

# Pre-amble using ideas from https://github.com/paul-gauthier/aider/blob/main/aider/coders/udiff_prompts.py
# Doesn't regress on the benchmark but improves average code generated and avoids empty comments.

# Add COT to each tool

instructions = """You are an expert software developer and your job is to edit code to complete the user's request.
You are diligent and tireless and always COMPLETELY IMPLEMENT the needed code!
You NEVER leave comments describing code without implementing it!
Always use best practices when coding.
Respect and use existing conventions, libraries, etc that are already present in the code base.

Your job is to make edits to the file to complete the user "# Request".

# Instructions
1. Use the ProposeProblemAnalysisAndPlan tool to analyze the user's request and construct a plan of keywords to search for and the changes to make.
2. Use the KeywordSearch tool to find the right places to make changes.
3. Use the AnalysisAndIdentification tool to determine which sections should be changed.
4. Use the SearchAndReplace tool to make the changes.
    - Keep whitespace and comments.
    - Make the minimum necessary search_and_replaces to make changes to the snippets.
    - Write multiple small changes instead of a single large change.


IMPORTANT: ONLY CALL ONE TOOL AT A TIME, WAIT UNTIL YOU SEE IF YOUR TOOL CALL SUCCEEDED OR FAILED BEFORE CALLING THE NEXT ONE.

You have access to the following tools:

# Tools
ProposeProblemAnalysisAndPlan - Break down the problem and identify important pieces of information that will be needed to solve the problem, such as the relevant keywords, the intended behavior, and the required imports. Describe the plan for the task, including the keywords to search and the modifications to make. Be sure to consider all imports that are required to complete the task.
To call this tool you MUST respond in the following xml format:

<ProposeProblemAnalysisAndPlan>
<Analysis>
Break down the problem and identify important pieces of information that will be needed to solve the problem, such as the relevant keywords, the intended behavior, and the required imports.
</Analysis>
<ProposedPlan>
Describe the plan for the task, including the keywords to search and the modifications to make. Be sure to consider all imports that are required to complete the task.
</ProposedPlan>
</ProposeProblemAnalysisAndPlan>

KeywordSearch - Use this tool to search for a keyword in the current code file as well as all relevant read-only code files. This is the keyword itself that you want to search for in the contents of the file, not the name of the file itself.
To call this tool you MUST respond in the following xml format:

<KeywordSearch>
<Justification>
Provide justification for searching the keyword in the given file.
</Justification>
<FileName>
Name of the file to search in. Ensure correct spelling. This is case sensitive.
</FileName>
<Keyword>
keyword to search for - e.g. function name, class name, variable name, ONLY SEARCH FOR ONE AT A TIME
</Keyword>
</KeywordSearch>

AnalysisAndIdentification - Identify and list the minimal changes that need to be made to the file, by listing all locations that should receive these changes and the changes to be made. Be sure to consider all imports that are required to complete the task.
To call this tool you MUST respond in the following xml format:

<AnalysisAndIdentification>
List out the changes that need to be made to the CURRENT FILE ONLY. List out all locations that should recieve these changes and what the changes should be.
</AnalysisAndIdentification>

SearchAndReplace - Use this tool to apply the changes one by one listed out in the AnalysisAndIdentification tool. This tool is great for when you change the function signature and want to update all the usages to that function.
If multiple SearchAndReplace calls are needed, call this tool multiple times. If you are going to call this tool multiple times, make sure to do it in seperate calls and wait for a SUCCESS or ERROR response from the user
before continuing to the next call.
To call this tool you MUST respond in the following xml format:

<SearchAndReplace>
<Justification>
Why this change is being made
</Justification>
<FileName>
Name of the file to make changes in. Ensure correct spelling. This is case sensitive.
</FileName>
<SectionId>
The section ID the original code belongs to.
</SectionId>
<OriginalCode>
The original lines of code. Be sure to add lines before and after to disambiguate the change.
</OriginalCode>
<NewCode>
The new code to replace the old code.
</NewCode>
</SearchAndReplace>

SubmitSolution - Use this tool to let the user know that you have completed all necessary steps in order to satisfy their request.
To call this tool you MUST respond in the following xml format:

<SubmitSolution>
<Justification>
Justification for why you are finished with your task.
</Justification>
</SubmitSolution>

ViewFile - Use this tool to view a file in the codebase.
To call this tool you MUST respond in the following xml format:

<ViewFile>
<Justification>
Justification for why you need to view this file
</Justification>
<FileName>
Name of the file, ensure correct spelling. This is case sensitive.
</FileName>
</ViewFile>

GetAdditionalContext - Use this tool to search the entire codebase for a keyword. This tool is useful when you need to find where a function is defined or used in the codebase.
To call this tool you MUST respond in the following xml format:

<GetAdditionalContext>
<Justification>
Provide justification for why you need additional context
</Justification>
<Keyword>
keyword to search for in order to get more additional context. This will perform a case insensitive search the entire codebase for this keyword, ONLY SEARCH FOR ONE KEYWORD AT A TIME
</Keyword>
</GetAdditionalContext>

Here is an example:
user:
# Request
modify the function post_process_rg_output to have a new parameter that specifies whether or not to truncate the output.

assistant:
<ProposeProblemAnalysisAndPlan>
<Analysis>
As I have not recieved any relevant code files to look at. I will need to locate the code file where the post_process_rg_output function is defined and add a new parameter to the function header that specifies whether or not to truncate the output.
I will then need to modify the logic of the function post_process_rg_output to gracefully handle the case where the new parameter is set to True. Finally, I will need to locate all the places where the post_process_rg_output function is called and update the call to include the new parameter.
</Analysis>
<ProposedPlan>
1. Use GetAdditionalContext with the keyword "post_process_rg_output" to find all files where the function is defined and used. From this I can extract the find the file where the function is defined.
2. Use the ViewFile tool to view the file where the function is defined and then locate the function definition. If the function definition is not immediately obvious upon viewing the file, I will use 
the KeywordSearch tool with the keyword "post_process_rg_output" on the file to find all occurences of the keyword in the file to locate the function definition.
3. Once the function definition is located, use the SearchAndReplace tool on the file in order to modify the post_process_rg_output function to include a new parameter that specifies whether or not to truncate the output and update the logic of the function to handle this. It is possible that I may need multiple 
SearchAndReplace calls to make all the necessary changes.
4. After the function is updated, use the output from step 1 to locate all the places where the post_process_rg_output function is called and update the call to include the new parameter. I should default the value to False as this is the current behavior.
</ProposedPlan>
</ProposeProblemAnalysisAndPlan>

user:
ProposeProblemAnalysisAndPlan: SUCCESS
Sounds like a great plan! Let's get started.

assistant:
<GetAdditionalContext>
<Justification>
I need to find where the function post_process_rg_output is defined and used in order to determine where the new parameter should be added and how it should be used.
</Justification>
<Keyword>
post_process_rg_output
</Keyword>
</GetAdditionalContext>

user:
SUCCESS

File: sweepai/core/context_pruning.py had the following matching lines of code:
28:from sweepai.utils.modify_utils import post_process_rg_output
729:                        rg_output_pretty = post_process_rg_output(repo_context_manager.cloned_repo.repo_dir, sweep_config, output)

File: sweepai/utils/modify_utils.py had the following matching lines of code:
5:def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):

assistant:
<ViewFile>
<Justification>
Based off of the results from the GetAdditionalContext tool, I need to view the file sweepai/utils/modify_utils.py to locate the function definition of post_process_rg_output
</Justification>
<FileName>
sweepai/utils/modify_utils.py
</FileName>
</ViewFile>

user:
SUCCESS

Here is the file:

<file filename="sweepai/utils/modify_utils.py">
<section id="A">
from collections import defaultdict
from sweepai.config.client import SweepConfig

# post process rip grep output to be more condensed
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
    processed_output = ""
    output_lines = output.split("\\n")
    # empty lines are present at end of output
    output_lines = [line for line in output_lines if line]
    file_output_dict = defaultdict(list)
    for line in output_lines:
        filename, content = line.split(":", 1)
        filename = filename[len(root_directory) + 1:]
        if not sweep_config.is_file_excluded_aggressive(root_directory, filename):
            file_output_dict[filename].append(content)
    
    # determine if we need to truncate the output
    total_output_length = sum([len(line) for content in file_output_dict.values() for line in content])
</section id="A">
<section id="B">
from collections import defaultdict
from sweepai.config.client import SweepConfig

# post process rip grep output to be more condensed
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
    processed_output = ""
    output_lines = output.split("\\n")
    # empty lines are present at end of output
    output_lines = [line for line in output_lines if line]
    file_output_dict = defaultdict(list)
    for line in output_lines:
        filename, content = line.split(":", 1)
        filename = filename[len(root_directory) + 1:]
        if not sweep_config.is_file_excluded_aggressive(root_directory, filename):
            file_output_dict[filename].append(content)
    
    # determine if we need to truncate the output
    total_output_length = sum([len(line) for content in file_output_dict.values() for line in content])
(Pdb++) print(chunks[1].get_snippet(add_ellipsis=False,add_lines=False))
    if total_output_length > 20000:
        for filename, content in file_output_dict.items():
            processed_output += f"File: {filename} had the following matching lines of code (some lines have been truncated):\\n"
            if len(content) < 3:
                for line in content:
                    processed_output += f"{line}\\n"
            else:
                line1 = content[0]
                line2 = content[-1]
                if len(line1) > 200:
                    line1 = line1[:20] + " ..."
                if len(line2) > 200:
                    line2 = line2[:20] + " ..."
                processed_output += f"{line1}\\n"
                processed_output += "...\\n"
                processed_output += f"{line2}\\n"
            processed_output += "\\n"
    else:
        for filename, content in file_output_dict.items():
            processed_output += f"File: {filename} had the following matching lines of code:\\n"
            for line in content:
                processed_output += f"{line}\\n"
            processed_output += "\\n"
    return processed_output

# try and find code inside chunk given various levels of indentation, and right strip the lines of code
# if successful returns the num of spaces required to find the code match
def manual_code_check(chunk: str, code: str) -> int:
    code_lines = [line.rstrip() for line in code.split("\\n")]
    # assume one indent is two spaces and check max 10 indents
    for indent in range(0, 40, 2):
        new_code_lines = [f"{' ' * indent}{line}" for line in code_lines]
        new_code = "\\n".join(new_code_lines)
        if new_code in chunk:
            return indent
    return -1
</section id="B">
</file filename="sweepai/utils/modify_utils.py">

assistant:
<KeywordSearch>
<Justification>
Search for the keyword post_process_rg_output in the file sweepai/utils/modify_utils.py to find the definition of the function.
</Justification>
<FileName>
sweepai/utils/modify_utils.py
</FileName>
<Keyword>
post_process_rg_output
</Keyword>
</KeywordSearch>

user:
SUCCESS

The keyword post_process_rg_output was found in sections A of sweepai/utils/modify_utils.py. They appear in the following places:
<section id="A"> (1 match)
from collections import defaultdict
from sweepai.config.client import SweepConfig

# post process rip grep output to be more condensed
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
    ^^^^^^^^^^^^^^^^^^^^^^
    processed_output = ""
    output_lines = output.split("\\n")
    # empty lines are present at end of output
    output_lines = [line for line in output_lines if line]
    file_output_dict = defaultdict(list)
    for line in output_lines:
        filename, content = line.split(":", 1)
        filename = filename[len(root_directory) + 1:]
        if not sweep_config.is_file_excluded_aggressive(root_directory, filename):
            file_output_dict[filename].append(content)
    
    # determine if we need to truncate the output
    total_output_length = sum([len(line) for content in file_output_dict.values() for line in content])
</section id="A">

assistant:
<SearchAndReplace>
<Justification>
Add a new parameter to the function post_process_rg_output to specify whether or not to truncate the output. The next step is to modify the logic of the function to gracefully handle the case where the new parameter is set to True.
</Justification>
<FileName>
sweepai/utils/modify_utils.py
</FileName>
<SectionId>
A
</SectionId>
<OriginalCode>
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
</OriginalCode>
<NewCode>
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str, truncate_output: bool):
</NewCode>
</SearchAndReplace>

user:
SUCCESS

The following changes have been applied:
```diff
--- 
+++ 
@@ -2,7 +2,7 @@
 from sweepai.config.client import SweepConfig
 
 # post process rip grep output to be more condensed
-def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
+def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str, truncate_output: bool):
     processed_output = ""
     output_lines = output.split("
 ")
```
You can continue to make changes to the code sections and call the SearchAndReplace tool again.

assistant:
<SearchAndReplace>
<Justification>
Update the logic so that when truncate_output is set to True, the output is truncated. We modify the if statement so that if truncate_output is set to False the previous behaviour is kept
</Justification>
<FileName>
sweepai/utils/modify_utils.py
</FileName>
<SectionId>
B
</SectionId>
<OriginalCode>
    if total_output_length > 20000:
</OriginalCode>
<NewCode>
    if truncate_output or total_output_length > 20000:
</NewCode>
</SearchAndReplace>

user:
SUCCESS

The following changes have been applied:
```diff
--- 
+++ 
@@ -17,7 +17,7 @@
     
     # determine if we need to truncate the output
     total_output_length = sum([len(line) for content in file_output_dict.values() for line in content])
-    if total_output_length > 20000:
+    if truncate_output or total_output_length > 20000:
         for filename, content in file_output_dict.items():
             processed_output += f"File: {filename} had the following matching lines of code (some lines have been truncated):
 "
```
You can continue to make changes to the code sections and call the SearchAndReplace tool again.

assistant:

<KeywordSearch>
<Justification>
The results from the GetAdditionalContext tool indicate that post_process_rg_output is called in sweepai/core/context_pruning.py. I need to locate that call in order to update the new parameter
</Justification>
<FileName>
sweepai/core/context_pruning.py
</FileName>
<Keyword>
post_process_rg_output
</Keyword>
</KeywordSearch>

user:
SUCCESS

The keyword post_process_rg_output was found in sections A and X of sweepai/core/context_pruning.py. They appear in the following places:
<section id="A"> (1 match)
import json
import os
import re
import subprocess
import textwrap
import time
import urllib

import networkx as nx
import openai
from attr import dataclass
from loguru import logger
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.agents.assistant_function_modify import MAX_CHARS
from sweepai.agents.assistant_wrapper import openai_retry_with_timeout
from sweepai.config.server import DEFAULT_GPT4_32K_MODEL
from sweepai.core.entities import Snippet
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.openai_proxy import get_client
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.str_utils import FASTER_MODEL_MESSAGE
from sweepai.utils.modify_utils import post_process_rg_output
                                       ^^^^^^^^^^^^^^^^^^^^^^
from sweepai.utils.tree_utils import DirectoryTree
from sweepai.config.client import SweepConfig

ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens

</section id="A">
<section id="X"> (1 match)
            if tool_call.function.name == "file_search":
                error_message = ""
                try:
                    similar_file_paths = "\\n".join(
                        [
                            f"- {path}"
                            for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                                function_path_or_dir
                            )
                        ]
                    )
                    valid_path = True
                except Exception:
                    similar_file_paths = ""
                    error_message = "FAILURE: This file path does not exist."
                if error_message:
                    output = error_message
                else:
                    output = (
                        f"SUCCESS: Here are the most similar file paths to {function_path_or_dir}:\\n{similar_file_paths}"
                        if valid_path
                        else "FAILURE: This file path does not exist. Please try a new path."
                    )
            elif tool_call.function.name == "keyword_search":
                error_message = ""
                keyword = function_input["keyword"]
                rg_command = ["rg", "-n", "-i" , keyword, repo_context_manager.cloned_repo.repo_dir]
                try:
                    result = subprocess.run(rg_command, text=True, capture_output=True)
                    output = result.stdout
                    if output:
                        # post process rip grep output to be more condensed
                        rg_output_pretty = post_process_rg_output(repo_context_manager.cloned_repo.repo_dir, sweep_config, output)
                                           ^^^^^^^^^^^^^^^^^^^^^^
                    else:
                        error_message = f"FAILURE: No results found for keyword: {keyword} in the entire codebase. Please try a new keyword. If you are searching for a function defintion try again with different whitespaces."
                except Exception as e:
                    logger.error(f"FAILURE: An Error occured while trying to find the keyword {keyword}: {e}")
                    error_message = f"FAILURE: An Error occured while trying to find the keyword {keyword}: {e}"
                if error_message:
                    output = error_message
                else:
                    output = (
                        f"SUCCESS: Here are the keyword_search results:\\n\\n{rg_output_pretty}"
                    )
</section id="X">

assistant:
<SearchAndReplace>
<Justification>
We must update all function calls of post_process_rg_output to include the new parameter truncate_output. We should default the value to False as this is the current behavior.
</Justification>
<FileName>
sweepai/core/context_pruning.py
</FileName>
<SectionId>
X
</SectionId>
<OriginalCode>
                        rg_output_pretty = post_process_rg_output(repo_context_manager.cloned_repo.repo_dir, sweep_config, output)
</OriginalCode>
<NewCode>
                        rg_output_pretty = post_process_rg_output(repo_context_manager.cloned_repo.repo_dir, sweep_config, output, False)
</NewCode>
</SearchAndReplace>

user:
SUCCESS

The following changes have been applied:
```diff
--- 
+++ 
@@ -549,7 +549,7 @@
                     output = result.stdout
                     if output:
                         # post process rip grep output to be more condensed
-                        rg_output_pretty = post_process_rg_output(repo_context_manager.cloned_repo.repo_dir, sweep_config, output)
+                        rg_output_pretty = post_process_rg_output(repo_context_manager.cloned_repo.repo_dir, sweep_config, output, False)
                     else:
                         error_message = f"FAILURE: No results found for keyword: {keyword} in the entire codebase. Please try a new keyword. If you are searching for a function defintion try again with different whitespaces."
                 except Exception as e:
```
You can continue to make changes to the code sections and call the SearchAndReplace tool again.

assistant:
<SubmitSolution>
<Justification>
A new parameter 'truncate_output' has been added to the function post_process_rg_output to specify whether or not to truncate the output. The logic of the function has been updated to gracefully handle the case where the new parameter is set to True. All function calls of post_process_rg_output have been updated to include the new parameter with a default value of False.
</Justification>
</SubmitSolution>

End of example.
"""

# 3. For each section that requires a change, use the search_and_replace function to make the changes. Use the analysis_and_identification section to determine which sections should be changed.
# - Make one change at a time.

# TODO: fuzzy search for keyword_search


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
        try:
            for relevant_file_path in relevant_filepaths:
                relevant_file_contents = read_file_with_fallback_encodings(
                    os.path.join(cloned_repo.repo_dir, relevant_file_path)
                )
                relevant_file_snippets = chunk_code(
                    relevant_file_contents, relevant_file_path, 1400, 500
                )
                relevant_file_contents_lines = relevant_file_contents.split("\n")
                # store relevant_file_path in modify_files_dict
                modify_files_dict[relevant_file_path]["chunks"] = [
                    "\n".join(
                        relevant_file_contents_lines[
                            max(snippet.start - 1, 0) : snippet.end
                        ]
                    )
                    for snippet in relevant_file_snippets
                ]
                modify_files_dict[relevant_file_path]["contents"] = relevant_file_contents
                modify_files_dict[relevant_file_path]["original_contents"] = relevant_file_contents
        except Exception as e:
            logger.error(
                f"Error occured while attempting to fetch contents for relevant file: {e}"
            )
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
                        tool_name, tool_call = assistant_generator.send(
                            "ERROR\nNo changes were made. Please continue working on your task."
                        )
                        
                elif tool_name == "no_tool_call":
                    error_message = ""
                    tool_name, tool_call = assistant_generator.send(
                        "ERROR\n No tool calls were made. If you are done, please use the SubmitSolution tool to indicate that you have completed the task. If you believe you are stuck, use the GetAdditionalContext tool to further explore the codebase or get additional context if necessary."
                    )
                elif tool_name == "ProposeProblemAnalysisAndPlan":
                    error_message = ""
                    tool_name, tool_call = assistant_generator.send(
                        "SUCCESS\nSounds like a great plan! Let's get started."
                    )
                elif tool_name == "AnalysisAndIdentification":
                    error_message = ""
                    tool_name, tool_call = assistant_generator.send(
                        "SUCCESS\nNice work! Now use the SearchAndReplace tool to make the listed changes one at a time. If there are multiple changes required, call the SearchAndReplace tool multiple times."
                    )
                elif tool_name == "ViewFile":
                    error_message = ""
                    file_name = tool_call["filename"].strip()
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
                        tool_name, tool_call = assistant_generator.send(
                            f'SUCCESS\n\nHere is the file:\n\n<file filename="{file_name}">\n{chunked_file_contents}\n</file filename="{file_name}">'
                        )
                    if error_message:
                        logger.debug(f"ERROR in ViewFile\n\n{error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n{error_message}"
                        )
                elif tool_name == "SearchAndReplace":
                    error_message = ""
                    for key in ["filename", "sectionid", "originalcode", "newcode"]:
                        if key not in tool_call:
                            error_message += f"Missing {key} in tool call.Call the tool again but this time provide the {key}.\n"
                    for _ in range(1): # this is super jank code but it works for now - only for easier error message handling
                        # ensure the file we are editting exists and is in modify_files_dict
                        if "filename" in tool_call:
                            file_name = tool_call["filename"].strip()
                            # if not in codebase or has not been created
                            if not os.path.exists(os.path.join(cwd, file_name)) and file_name not in modify_files_dict:
                                error_message += f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!\n"
                            if file_name not in modify_files_dict:
                                error_message += f"You have not viewed {file_name} yet! Are you CERTAIN this is the file you want to modify? If so, view the file first with the ViewFile tool and then call the SearchAndReplace tool again.\n"
                        if error_message:
                            break
                        success_message = ""
                        section_letter = tool_call["sectionid"].strip()
                        section_id = excel_col_to_int(section_letter)
                        old_code = tool_call["originalcode"].strip("\n")
                        new_code = tool_call["newcode"].strip("\n")
                        # get the chunks and contents for the file
                        file_chunks = deepcopy(modify_files_dict[file_name]['chunks'])  
                        file_contents = modify_files_dict[file_name]['contents']
                        warning_message = ""
                        if section_id >= len(file_chunks):
                            error_message = f"Could not find section {section_letter} in file {file_name}, which has {len(file_chunks)} sections."
                            break
                        elif section_id < 0:
                            error_message = f"The section ID {section_letter} can not be parsed."
                            break

                        # fetch the chunk of code we will be modifying
                        try:
                            current_chunk = file_chunks[section_id]
                        except Exception:
                            error_message = f"Could not fetch the chunk of code for section {section_letter} in file {file_name}. Make sure you are modifying the correct file {file_name}"
                            break
                        
                        # check to see that the old_code is in the new_code by trying all possible indentations
                        correct_indent, rstrip_old_code = manual_code_check(current_chunk, old_code)
                        # if the old_code couldn't be found in the chunk we need to let the llm know
                        if old_code not in current_chunk and correct_indent == -1:
                            chunks_with_old_code = [
                                index
                                for index, chunk in enumerate(file_chunks)
                                if old_code in chunk or manual_code_check(chunk, old_code)[0] != -1
                            ]
                            chunks_with_old_code = chunks_with_old_code[:5]
                            error_message = f"The OriginalCode provided does not appear to be present in section {section_letter}. The OriginalCode contains:\n```\n{old_code}\n```\nBut section {section_letter} in {file_name} has code:\n```\n{current_chunk}\n```"
                            if chunks_with_old_code:
                                error_message += "\n\nDid you mean one of the following sections?"
                                error_message += "\n".join(
                                    [
                                        f'\n<section id="{int_to_excel_col(index + 1)}">\n{file_chunks[index]}\n</section>\n```'
                                        for index in chunks_with_old_code
                                    ]
                                )
                            else:
                                error_message += "\n\nNo changes were applied due to this error. Make another replacement. It seems there may be a spelling or indentation error as the OriginalCode could not be found in the code file. Ensure that your indents have the correct amount of spaces (e.g. 2 or 4). Consider missing or misplaced whitespace, comments or delimiters. Then, identify what should be the correct OriginalCode should be, and make another replacement with the corrected OriginalCode."
                            break
                        # ensure old_code and new_code has the correct indents
                        new_code_lines = new_code.split("\n")
                        new_code = "\n".join(f'{correct_indent*" "}{line}' for line in new_code_lines)
                        if rstrip_old_code:
                            old_code_lines = [line.rstrip() for line in old_code.split("\n")]
                        else:
                            old_code_lines = old_code.split("\n")
                        old_code = "\n".join(f'{correct_indent*" "}{line}' for line in old_code_lines)
                        # before we apply changes make sure old_code is unique inside current_chunk
                        current_chunk_occurences = current_chunk.count(old_code)
                        if current_chunk_occurences > 1:
                            error_message = f"The OriginalCode is not unique in the section {section_letter}. It appears {current_chunk_occurences} times! Make sure the OriginalCode is unique in the section you are modifying!"
                            break

                        # apply changes
                        new_chunk = current_chunk.replace(old_code, new_code, 1)
                        if new_chunk == current_chunk:
                            logger.warning("No changes were made to the code.")
                        
                        file_chunks[section_id] = new_chunk
                        new_contents = file_contents.replace(
                            current_chunk, new_chunk, 1
                        )

                        # Check if changes were made
                        if new_contents == file_contents:
                            logger.warning("No changes were made to the code.")
                            error_message = "No changes were made, make sure OriginalCode and NewCode are not the same."
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
                                error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code.\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the SearchAndReplace with different changes that yield valid code. HINT: To ensure the changes are being applied in the correct place, make sure OriginalCode is descriptive enough!"
                                break
                    if error_message:
                        logger.error(f"Error occured in SearchAndReplace tool: {error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n {error_message}"
                        )

                    if not error_message:
                        success_message = (
                            f"SUCCESS\n\nThe following changes have been applied to {file_name}:\n\n"
                            + generate_diff(file_contents, new_contents)
                        ) + f"{warning_message}\n\nYou can continue to make changes to the code sections and call the SearchAndReplace tool again, or go back to searching for keywords using the KeywordSearch tool, which is great for finding all definitions or usages of a function or class."
                        # set contents
                        modify_files_dict[file_name]['contents'] = new_contents
                        modify_files_dict[file_name]['chunks'] = file_chunks
                        logger.info(success_message)
                        
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\n\n{success_message}"
                        )
                elif tool_name == "GetAdditionalContext":
                    error_message = ""
                    keyword = tool_call["keyword"].strip()
                    rg_command = ["rg", "-n", "-i" , f'"{keyword}"', cwd]
                    try:
                        # update the cloned repo before running ripgrep as it is possible some of the files have been editted
                        for file_name, file_data in modify_files_dict.items():
                            cloned_repo.update_file(file_name, file_data["contents"])
                    except Exception as e:
                        logger.error(f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}")
                        error_message = f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}\n"
                        # attempt to undo the updates
                        for file_name, file_data in modify_files_dict.items():
                            cloned_repo.update_file(file_name, file_data["original_contents"])
                        
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
                            cloned_repo.update_file(file_name, file_data["original_contents"])
                    except Exception as e:
                        logger.error(f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}")
                        error_message = f"FAILURE: An Error occured while trying to update the cloned repo on file {file_name}: {e}"

                    if error_message:
                        logger.debug(f"ERROR in GetAdditionalContext\n\n{error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n{error_message}"
                        )
                    else:
                        logger.debug(f"SUCCESS\n\nHere are the GetAdditionalContext results:\n{rg_output_pretty}\n\n")
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\n\nHere are the GetAdditionalContext results:\n{rg_output_pretty}\n\n You can use the new context to revise your plan by calling the ProposeProblemAnalysisAndPlan tool again. You can also call the AnalysisAndIdentification tool again."
                        )
                elif tool_name == "KeywordSearch":
                    error_message = ""
                    success_message = ""
                    for key in ["filename", "justification", "keyword"]:
                        if key not in tool_call:
                            logger.debug(f"No {key} was provided in the KeywordSearch tool call. Call the tool again but this time provide the {key}.")
                            error_message = f"No {key} was provided in the KeywordSearch tool call. Call the tool again but this time provide the {key}."
                            break

                    if "filename" in tool_call:
                        file_name = tool_call["filename"].strip()
                        full_file_path = os.path.join(cwd, file_name)
                        # not in codebase and also not a newly created file
                        if not os.path.exists(full_file_path) and file_name not in modify_files_dict:
                            logger.debug(f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!")
                            error_message = f"The file {file_name} does not exist. Make sure that you have spelled the file name correctly!"
                    
                    # if no issues continue with search
                    if not error_message:
                        keyword = tool_call["keyword"].strip()
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
                            logger.debug(f"The keyword {keyword} does not appear to be present in the file: {file_name}. Consider missing or misplaced whitespace, comments or delimiters in the keyword.")
                            error_message = f"The keyword {keyword} does not appear to be present in the file: {file_name}. Consider missing or misplaced whitespace, comments or delimiters in the keyword."
                        else:
                            # for matches inside current code file
                            sections_message = english_join(
                                [
                                    int_to_excel_col(match_index + 1)
                                    for match_index in match_indices
                                ]
                            )
                            starter_message = f"The keyword {keyword} was found in sections {sections_message} of {file_name}. They appear in the following places:\n\n"
                            success_message += (
                                build_keyword_search_match_results(
                                    match_indices,
                                    file_chunks,
                                    keyword,
                                    starter_message,
                                    readonly=True
                                )
                            )

                    if error_message:
                        logger.debug(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n{error_message}"
                        )
                    else:
                        logger.debug(success_message)
                        if relevant_filepaths:
                            suffix = f"\n\nMake additional keyword_search calls to find other keywords or start making changes by calling the search_and_replace function. Remember that you may only edit the CURRENT file {file_path} and may not edit any of the READONLY files {english_join(relevant_filepaths)}."
                        else:
                            suffix = f"\n\nMake additional keyword_search calls to find other keywords or start making changes by calling the search_and_replace function. Remember that you may only edit the CURRENT file {file_path}."
                        tool_name, tool_call = assistant_generator.send(
                            f"{success_message}{suffix}"
                        )
                else:
                    tool_name, tool_call = assistant_generator.send(
                        f"ERROR\nUnexpected tool name: {tool_name}"
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
    import os
    # request = "Convert any all logger.errors to logger.exceptions in on_ticket.py"
    request = """Split any logger.errors to:
logger = Logger()
logger.errors()
in on_ticket.py""" # this causes a pylint error so it's great for testing
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
        chat_logger=ChatLogger(
            {
                "username": "kevinlu1248",
                "title": request
            }
        ),
        additional_messages=additional_messages,
        ticket_progress=TicketProgress(tracking_id="test_remove_assistant_1"),
    )