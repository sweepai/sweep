from copy import deepcopy
import os
import json
import subprocess
import traceback
from collections import defaultdict

from loguru import logger

from sweepai.agents.assistant_functions import (
    chain_of_thought_schema,
    keyword_search_schema,
    search_and_replace_schema,
    submit_schema,
)
from sweepai.agents.assistant_wrapper import openai_assistant_call
from sweepai.agents.agent_utils import MAX_CHARS, ensure_additional_messages_length
from sweepai.config.client import SweepConfig
from sweepai.config.server import USE_ASSISTANT
from sweepai.core.entities import AssistantRaisedException, FileChangeRequest, Message, Snippet
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.diff import generate_diff
from sweepai.utils.file_utils import read_file_with_fallback_encodings
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.utils import chunk_code, get_check_results
from sweepai.utils.modify_utils import post_process_rg_output

# Pre-amble using ideas from https://github.com/paul-gauthier/aider/blob/main/aider/coders/udiff_prompts.py
# Doesn't regress on the benchmark but improves average code generated and avoids empty comments.

instructions = """You are an expert software developer and your job is to edit code to complete the user's request.
You are diligent and tireless and always COMPLETELY IMPLEMENT the needed code!
You NEVER leave comments describing code without implementing it!
Your job is to make edits to the file to complete the user "# Request".
# Instructions
1. Use the propose_problem_analysis_and_plan function to analyze the user's request and construct a plan of keywords to search for and the changes to make.
2. Use the keyword_search function to find the right places to make changes.
3. Use the search_and_replace function to make the changes.
    - Keep whitespace and comments.
    - Make the minimum necessary search_and_replaces to make changes to the snippets.
    - Write multiple small changes instead of a single large change.
When you have completed the task, call the submit function.
"""

# Add COT to each tool

new_instructions = """You are an expert software developer and your job is to edit code to complete the user's request.
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

IMPORTANT: If you believe you are missing important information or context in any of the steps above use the GetAdditionalContext tool to further explore the codebase or get additional context if necessary.

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
Provide justification for searching the keyword.
</Justification>
<Keyword>
keyword to search for - e.g. function name, class name, variable name
</Keyword>
</KeywordSearch>

AnalysisAndIdentification - Identify and list the minimal changes that need to be made to the file, by listing all locations that should receive these changes and the changes to be made. Be sure to consider all imports that are required to complete the task.
To call this tool you MUST respond in the following xml format:

<AnalysisAndIdentification>
List out the changes that need to be made to the CURRENT FILE ONLY. List out all locations that should recieve these changes and what the changes should be.
</AnalysisAndIdentification>

SearchAndReplace - Use this tool to apply the changes one by one listed out in the AnalysisAndIdentification tool. This tool is great for when you change the function signature and want to update all the usages to that function.
If multiple SearchAndReplace calls are needed, call this tool multiple times. To call this tool you MUST respond in the following xml format:

<SearchAndReplace>
<SectionId>
The section ID the original code belongs to.
</SectionId>
<OriginalCode>
The original lines of code. Be sure to add lines before and after to disambiguate the change.
</OriginalCode>
<NewCode>
The new code to replace the old code.
</NewCode>
<Justification>
Why this change is being made
</Justification>
</SearchAndReplace>

SubmitSolution - Use this tool to let the user know that you have completed all necessary steps in order to satisfy their request.
To call this tool you MUST respond in the following xml format:

<SubmitSolution>
<Justification>
Justification for why you are finished with your task.
</Justification>
</SubmitSolution>

<GetAdditionalContext>
<Justification>
Provide justification for why you need additional context
</Justification>
<Keyword>
keyword to search for in order to get more additional context. This will search the entire codebase for this keyword
</Keyword>
</GetAdditionalContext>
"""

if not USE_ASSISTANT:
    instructions = new_instructions

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
            success_message += f"<readonly_section>{num_matches_message}\n{match_display}\n</readonly_section>\n"
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


# @file_cache(ignore_params=["file_path", "chat_logger"])
def function_modify(
    request: str,
    file_path: str,
    file_contents: str,
    cloned_repo: ClonedRepo,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = None,
    start_line: int = -1,
    end_line: int = -1,
    ticket_progress: TicketProgress | None = None,
    assistant_conversation: AssistantConversation | None = None,
    seed: int = None,
    relevant_filepaths: list[str] = [],
    fcrs: list[FileChangeRequest]=[],
    cwd: str | None = None,
):
    try:

        def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
            if assistant_conversation:
                assistant_conversation.update_from_ids(
                    assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
                )
            ticket_progress.save()

        current_contents = file_contents
        relevant_file_contents = defaultdict(str)
        # get code for relevant filepaths
        try:
            for relevant_file_path in relevant_filepaths:
                relevant_file_content = read_file_with_fallback_encodings(
                    os.path.join(cloned_repo.repo_dir, relevant_file_path)
                )
                relevant_file_contents[relevant_file_path] = relevant_file_content
        except Exception as e:
            logger.error(
                f"Error occured while attempting to fetch contents for relevant file: {e}"
            )
        initial_check_results = get_check_results(file_path, current_contents)

        original_snippets = chunk_code(current_contents, file_path, 700, 200)
        # original_snippets = chunk_code(current_contents, file_path, 1500, 200)

        relevant_file_snippets: dict[str, list[Snippet]] = defaultdict(list)
        # now we chunk relevant file contents
        for relevant_file_path, relevant_file_content in relevant_file_contents.items():
            relevant_file_snippet = chunk_code(
                relevant_file_content, relevant_file_path, 700, 200
            )
            relevant_file_snippets[relevant_file_path] = relevant_file_snippet

        file_contents_lines = current_contents.split("\n")
        chunks = [
            "\n".join(file_contents_lines[max(snippet.start - 1, 0) : snippet.end])
            for snippet in original_snippets
        ]

        # split our relevant files into chunks
        relevant_file_chunks = defaultdict(list)
        for relevant_file_path, relevant_file_content in relevant_file_contents.items():
            relevant_file_contents_lines = relevant_file_content.split("\n")
            relevant_file_chunks[relevant_file_path] = [
                "\n".join(
                    relevant_file_contents_lines[
                        max(snippet.start - 1, 0) : snippet.end
                    ]
                )
                for snippet in relevant_file_snippets[relevant_file_path]
            ]
        code_sections = []  # TODO: do this for the new sections after modifications
        current_code_section = ""
        for i, chunk in enumerate(chunks):
            idx = int_to_excel_col(i + 1)
            section_display = f'<section id="{idx}">\n{chunk}\n</section id="{idx}">'
            if len(current_code_section) + len(section_display) > MAX_CHARS - 1000:
                code_sections_string = f"# Code\nFile path:{file_path}\n<sections>\n{current_code_section}\n</sections>"
                code_sections.append(code_sections_string)
                current_code_section = section_display
            else:
                current_code_section += "\n" + section_display
        current_code_section = current_code_section.strip("\n")
        code_sections.append(f"<current_file_to_modify filename=\"{file_path}\">\n{current_code_section}\n</current_file_to_modify>")
        fcrs_message = generate_status_message(file_path, fcrs)
        additional_messages = [
            Message(
                role="user",
                content=f"# Request\n{request}\n\n{fcrs_message}",
            ),
            *reversed([
                Message(
                    role="user",
                    content=code_section,
                )
                for code_section in code_sections
            ]),
        ] + additional_messages
        tools = [
            {"type": "function", "function": chain_of_thought_schema},
            {"type": "function", "function": keyword_search_schema},
            # {"type": "function", "function": view_sections_schema},
            {"type": "function", "function": search_and_replace_schema},
        ]
        if not USE_ASSISTANT:
            tools.append({"type": "function", "function": submit_schema})
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
            tools=tools,
        )

        try:
            done_counter = 0
            tool_name, tool_call = assistant_generator.send(None)
            for i in range(100):  # TODO: tune this parameter
                print(tool_name, json.dumps(tool_call, indent=2))
                if tool_name == "done" or tool_name == "submit":
                    diff = generate_diff(file_contents, current_contents)
                    if diff:
                        break
                    else:
                        done_counter += 1
                        if done_counter >= 3:
                            break
                        tool_name, tool_call = assistant_generator.send(
                            "ERROR\nNo changes were made. Please continue working on your task."
                        )
                elif tool_name == "propose_problem_analysis_and_plan":
                    tool_name, tool_call = assistant_generator.send(
                        "SUCCESS\nSounds like a great plan! Let's start by using the keyword_search function to find the right places to make changes, and the search_and_replace function to make the changes."
                    )
                elif tool_name == "search_and_replace":
                    error_message = ""
                    success_message = ""
                    new_contents = current_contents
                    new_chunks = deepcopy(chunks)  # deepcopy
                    success_messages = []
                    warning_message = ""
                    error_index = 0
                    if "replaces_to_make" not in tool_call:
                        error_message = "No replaces_to_make found in tool call."
                    elif len(tool_call["replaces_to_make"]) == 0:
                        error_message = "replace_to_make should not be empty."
                    else:
                        # TODO: add roll backwards functionality
                        for index, replace_to_make in enumerate(
                            tool_call["replaces_to_make"]
                        ):
                            # error_index is last index before we break from this for loop
                            error_index = index
                            current_new_contents = new_contents
                            # only do this is replace_to_make is a dict
                            if not isinstance(replace_to_make, dict):
                                continue
                            for key in ["section_id", "old_code", "new_code"]:
                                if key not in replace_to_make:
                                    error_message = f"Missing {key} in replace_to_make."
                                    break
                                if not isinstance(replace_to_make[key], str):
                                    error_message = f"{key} should be a string."
                                    break

                            if error_message:
                                break

                            section_letter = replace_to_make["section_id"]
                            section_id = excel_col_to_int(section_letter)
                            old_code = replace_to_make["old_code"].strip("\n")
                            new_code = replace_to_make["new_code"].strip("\n")

                            if section_id >= len(chunks):
                                error_message = f"Could not find section {section_letter} in file {file_path}, which has {len(chunks)} sections."
                                break
                            chunk = new_chunks[section_id]
                            if old_code not in chunk:
                                chunks_with_old_code = [
                                    index
                                    for index, chunk in enumerate(chunks)
                                    if old_code in chunk
                                ]
                                chunks_with_old_code = chunks_with_old_code[:5]
                                error_message = f"The old_code in the {index}th replace_to_make does not appear to be present in section {section_letter}. The old_code contains:\n```\n{old_code}\n```\nBut section {section_letter} has code:\n```\n{chunk}\n```"
                                if chunks_with_old_code:
                                    error_message += "\n\nDid you mean one of the following sections?"
                                    error_message += "\n".join(
                                        [
                                            f'\n<section id="{int_to_excel_col(index + 1)}">\n{chunks[index]}\n</section>\n```'
                                            for index in chunks_with_old_code
                                        ]
                                    )
                                else:
                                    error_message += "\n\nMake another replacement. In the analysis_and_identification, first identify the indentation or spelling error. Consider missing or misplaced whitespace, comments or delimiters. Then, identify what should be the correct old_code, and make another replacement with the corrected old_code."
                                break
                            new_chunk = chunk.replace(old_code, new_code, 1)
                            if new_chunk == chunk:
                                logger.warning("No changes were made to the code.")
                            new_chunks[section_id] = new_chunk
                            current_new_contents = current_new_contents.replace(
                                chunk, new_chunk, 1
                            )

                            # Check if changes we're made
                            if new_contents == current_contents:
                                logger.warning("No changes were made to the code.")

                            # Check if the changes are valid
                            if not error_message:
                                check_results = get_check_results(file_path, new_contents)
                                check_results_message = check_results.is_worse_than_message(initial_check_results)
                                failing_parse = check_results.parse_error_message if not initial_check_results.parse_error_message else ""
                                current_diff = generate_diff(
                                    current_contents, new_contents
                                )
                                if not failing_parse:
                                    success_messages.append(
                                        f"The following changes have been applied:\n```diff\n{current_diff}\n```\nYou can continue to make changes to the code sections and call the SearchAndReplace tool again."
                                    )
                                    if check_results_message:
                                        warning_message = f"\n\nWARNING\n\n{check_results_message}"
                                else:
                                    error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code with the following error message:\n```\n{failing_parse}\n```\n\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the SearchAndReplace with different changes that yield valid code."
                                    break
                                new_contents = current_new_contents
                    if not error_message:
                        chunks = new_chunks
                    if not error_message and new_contents == current_contents:
                        error_message = "No changes were made, make sure old_code and new_code are not the same."

                    # if not error_message:
                    #     # If the initial code failed, we don't need to/can't check the new code
                    #     is_valid, message = (
                    #         (True, "")
                    #         if not initial_code_valid
                    #         else check_code(file_path, new_contents)
                    #     )
                    #     if is_valid:
                    #         diff = generate_diff(current_contents, new_contents)
                    #         current_contents = new_contents

                    #         # Re-initialize
                    #         success_message = f"The following changes have been applied:\n```diff\n{diff}\n```\nYou can continue to make changes to the code sections and call the `search_and_replace` function again."
                    #     else:
                    #         diff = generate_diff(current_contents, new_contents)
                    #         error_message = f"No changes have been applied becuase invalid code changes have been applied. You requested the following changes:\n\n```diff\n{diff}\n```\n\nBut it produces invalid code with the following error message:\n```\n{message}\n```\n\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the search_and_replace with different changes that yield valid code."
                    if not error_message:
                        success_message = (
                            "SUCCESS\n\nThe following changes have been applied:\n\n"
                            + generate_diff(current_contents, new_contents)
                        ) + f"{warning_message}\n\nYou can continue to make changes to the code sections and call the SearchAndReplace tool again, or go back to searching for keywords using the KeywordSearch tool, which is great for finding all definitions or usages of a function or class."
                        # set contents
                        current_contents = new_contents

                    if error_message:
                        logger.error(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            "ERROR\n\n"
                            + "\n".join(
                                f"{i}th replace to make:\n\n{message}"
                                for i, message in enumerate(success_messages)
                            )
                            + f"\n{error_index}th replace to make: "
                            + error_message
                        )
                    else:
                        logger.info(success_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\n\n{success_message}"
                        )
                elif tool_name == "keyword_search":
                    error_message = ""
                    success_message = ""
                    for key in ["justification", "keyword"]:
                        if key not in tool_call:
                            error_message = f"Missing {key} in keyword_search."
                            break

                    if not error_message:
                        keyword = tool_call["keyword"].strip()
                        match_indices = []
                        match_context_indices = []
                        relevant_file_match_indices: dict[str, list[int]] = defaultdict(
                            list
                        )
                        relevant_file_match_context_indices: dict[str, list[int]] = defaultdict(
                            list
                        )
                        # search current code file
                        for i, chunk in enumerate(chunks):
                            if keyword in chunk:
                                match_indices.append(i)
                                match_context_indices.append(max(0, i - 1))
                                match_context_indices.append(i)
                                match_context_indices.append(min(len(chunks) - 1, i + 1))
                        # search all relevant code files
                        for (
                            relevant_file_path,
                            relevant_file_chunk_group,
                        ) in relevant_file_chunks.items():
                            for i, chunk in enumerate(relevant_file_chunk_group):
                                if keyword in chunk:
                                    relevant_file_match_indices[
                                        relevant_file_path
                                    ].append(i)
                                    relevant_file_match_context_indices[
                                        relevant_file_path
                                    ].append(max(0, i - 1))
                                    relevant_file_match_context_indices[
                                        relevant_file_path
                                    ].append(i)
                                    relevant_file_match_context_indices[
                                        relevant_file_path
                                    ].append(
                                        min(len(relevant_file_chunk_group) - 1, i + 1)
                                    )

                        match_indices = sorted(list(set(match_indices)))
                        match_context_indices = sorted(list(set(match_context_indices)))
                        relevant_file_match_indices = {
                            k: sorted(list(set(v)))
                            for k, v in relevant_file_match_indices.items()
                        }
                        relevant_file_match_context_indices = {
                            k: sorted(list(set(v)))
                            for k, v in relevant_file_match_context_indices.items()
                        }
                        if not match_indices and not relevant_file_match_indices:
                            error_message = f"The keyword {keyword} does not appear to be present in the current and relevant code files. Consider missing or misplaced whitespace, comments or delimiters."
                        else:
                            # for matches inside current code file
                            if match_indices:
                                sections_message = english_join(
                                    [
                                        int_to_excel_col(match_index + 1)
                                        for match_index in match_indices
                                    ]
                                )
                                starter_message = f"CURRENT FILE\n\nThe keyword {keyword} was found in sections {sections_message} of the CURRENT file {file_path}, which you MAY modify. They appear in the following places:\n\n"
                                success_message += build_keyword_search_match_results(
                                    match_context_indices, chunks, keyword, starter_message
                                )
                                if relevant_file_match_indices:
                                    success_message += "\n\n"
                            else:
                                success_message += f"The keyword {keyword} was not found in the current file. However, it was found in the following relevant READONLY file(s).\n\n"
                            # for matches inside relevant code files
                            if relevant_file_match_indices:
                                sections_message = english_join(
                                    [
                                        int_to_excel_col(match_index + 1)
                                        for match_index in match_indices
                                    ]
                                )
                                also_keyword = "also " if match_indices else ""
                                for (
                                    relevant_file_path,
                                    relevant_file_match_indices,
                                ), (
                                    _,
                                    relevant_file_match_context_indices,
                                ) in zip(relevant_file_match_indices.items(), relevant_file_match_context_indices.items()):
                                    sections_message = english_join(
                                        [
                                            int_to_excel_col(match_index + 1)
                                            for match_index in relevant_file_match_indices
                                        ]
                                    )
                                    starter_message = f"READONLY FILES\n\nThe keyword {keyword} was {also_keyword}found in sections {sections_message} of the READONLY file {relevant_file_path}, which you MAY NOT modify. They appear in the following places:\n\n"
                                    success_message += (
                                        build_keyword_search_match_results(
                                            relevant_file_match_context_indices,
                                            relevant_file_chunks[relevant_file_path],
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
                elif tool_name == "view_sections":
                    error_message = ""
                    success_message = ""
                    if "section_ids" not in tool_call:
                        error_message = "No section_ids found in tool call."

                    if not isinstance(tool_call["section_ids"], list):
                        error_message = "section_ids should be a list."

                    if not len(tool_call["section_ids"]):
                        error_message = "section_ids should not be empty."

                    # get one section before and after each section
                    section_indices = set()
                    for section_id in tool_call["section_ids"]:
                        section_index = excel_col_to_int(section_id)
                        section_indices.update(
                            (
                                int_to_excel_col(max(1, section_index - 1)),
                                int_to_excel_col(min(len(chunks), section_index)),
                                int_to_excel_col(min(len(chunks), section_index + 1)),
                                int_to_excel_col(min(len(chunks), section_index + 2)),
                            )
                        )
                    section_indices = sorted(list(section_indices))
                    if not error_message:
                        success_message = "Here are the sections:" + "\n\n".join(
                            [
                                f"<section id='{section_id}'>\n{chunks[excel_col_to_int(section_id)]}\n</section>"
                                for section_id in section_indices
                            ]
                        )

                    if error_message:
                        logger.debug(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n{error_message}"
                        )
                    else:
                        logger.debug(success_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\n{success_message}\n\nMake additional view_sections or keyword_search calls to find other keywords or sections or continue to make changes by calling the search_and_replace function."
                        )
                else:
                    tool_name, tool_call = assistant_generator.send(
                        f"ERROR\nUnexpected tool name: {tool_name}"
                    )
            else:
                logger.error("Too many iterations.")
        except StopIteration:
            pass
        diff = generate_diff(file_contents, current_contents)
        if diff:
            logger.info("Changes made:\n\n" + diff)
        else:
            logger.warning("No changes were made.")
        if current_contents != file_contents:
            return current_contents
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

def function_modify_unstable(
    request: str,
    file_path: str,
    file_contents: str,
    cloned_repo: ClonedRepo,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = None,
    start_line: int = -1,
    end_line: int = -1,
    ticket_progress: TicketProgress | None = None,
    assistant_conversation: AssistantConversation | None = None,
    seed: int = None,
    relevant_filepaths: list[str] = [],
    cwd: str | None = None,
    fcrs: list[FileChangeRequest]=[]
):
    try:
        logger.info("Starting function_modify_unstable")
        def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
            if assistant_conversation:
                assistant_conversation.update_from_ids(
                    assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
                )
            ticket_progress.save()

        current_contents = file_contents
        relevant_file_contents = defaultdict(str)
        sweep_config: SweepConfig = SweepConfig()
        # get code for relevant filepaths
        try:
            for relevant_file_path in relevant_filepaths:
                relevant_file_content = read_file_with_fallback_encodings(
                    os.path.join(cloned_repo.repo_dir, relevant_file_path)
                )
                relevant_file_contents[relevant_file_path] = relevant_file_content
        except Exception as e:
            logger.error(
                f"Error occured while attempting to fetch contents for relevant file: {e}"
            )
        initial_check_results = get_check_results(file_path, current_contents)

        original_snippets = chunk_code(current_contents, file_path, 700, 200)
        # original_snippets = chunk_code(current_contents, file_path, 1500, 200)

        relevant_file_snippets: dict[str, list[Snippet]] = defaultdict(list)
        # now we chunk relevant file contents
        for relevant_file_path, relevant_file_content in relevant_file_contents.items():
            relevant_file_snippet = chunk_code(
                relevant_file_content, relevant_file_path, 700, 200
            )
            relevant_file_snippets[relevant_file_path] = relevant_file_snippet

        file_contents_lines = current_contents.split("\n")
        chunks = [
            "\n".join(file_contents_lines[max(snippet.start - 1, 0) : snippet.end])
            for snippet in original_snippets
        ]

        # split our relevant files into chunks
        relevant_file_chunks = defaultdict(list)
        for relevant_file_path, relevant_file_content in relevant_file_contents.items():
            relevant_file_contents_lines = relevant_file_content.split("\n")
            relevant_file_chunks[relevant_file_path] = [
                "\n".join(
                    relevant_file_contents_lines[
                        max(snippet.start - 1, 0) : snippet.end
                    ]
                )
                for snippet in relevant_file_snippets[relevant_file_path]
            ]
        code_sections = []  # TODO: do this for the new sections after modifications
        current_code_section = ""
        for i, chunk in enumerate(chunks):
            idx = int_to_excel_col(i + 1)
            section_display = f'<section id="{idx}">\n{chunk}\n</section id="{idx}">'
            if len(current_code_section) + len(section_display) > MAX_CHARS - 1000:
                code_sections_string = f"# Code\nFile path:{file_path}\n<sections>\n{current_code_section}\n</sections>"
                code_sections.append(code_sections_string)
                current_code_section = section_display
            else:
                current_code_section += "\n" + section_display
        current_code_section = current_code_section.strip("\n")
        code_sections.append(f"<current_file_to_modify filename=\"{file_path}\">\n{current_code_section}\n</current_file_to_modify>")
        fcrs_message = generate_status_message(file_path, fcrs)
        additional_messages = [
            Message(
                role="user",
                content=f"# Request\n{request}\n\n{fcrs_message}",
            ),
            *reversed([
                Message(
                    role="user",
                    content=code_section,
                )
                for code_section in code_sections
            ]),
        ] + additional_messages
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
                    diff = generate_diff(file_contents, current_contents)
                    if diff:
                        break
                    else:
                        done_counter += 1
                        if done_counter >= 3:
                            break
                        tool_name, tool_call = assistant_generator.send(
                            "ERROR\nNo changes were made. Please continue working on your task."
                        )
                elif tool_name == "no_tool_call":
                    tool_name, tool_call = assistant_generator.send(
                        "ERROR\n No tool calls were made. If you are done, please use the SubmitSolution tool to indicate that you have completed the task. If you believe you are stuck, use the GetAdditionalContext tool to further explore the codebase or get additional context if necessary."
                    )
                elif tool_name == "SubmitSolution":
                    diff = generate_diff(file_contents, current_contents)
                    if diff:
                        break
                    else:
                        done_counter += 1
                        if done_counter >= 3:
                            break
                        tool_name, tool_call = assistant_generator.send(
                            "ERROR\nNo changes were made. Please continue working on your task."
                        )
                elif tool_name == "ProposeProblemAnalysisAndPlan":
                    tool_name, tool_call = assistant_generator.send(
                        "SUCCESS\nSounds like a great plan! Let's start by using the KeywordSearch tool to find the right places to make changes, and the SearchAndReplace tool to make the changes."
                    )
                elif tool_name == "AnalysisAndIdentification":
                    tool_name, tool_call = assistant_generator.send(
                        "SUCCESS\nNice work! Now use the SearchAndReplace tool to make the listed changes one at a time. If there are multiple changes required, call the SearchAndReplace tool multiple times."
                    )
                elif tool_name == "SearchAndReplace":
                    error_message = ""
                    success_message = ""
                    new_chunks = deepcopy(chunks)  # deepcopy
                    success_messages = []
                    warning_message = ""
                    if "sectionid" not in tool_call:
                        error_message = "No SectionId was provided in the tool call. Call the tool again but this time provide the SectionId.\n"
                    if "originalcode" not in tool_call:
                        error_message += "No OriginalCode was provided in the tool call. Call the tool again but this time provide the OriginalCode.\n"
                    if "newcode" not in tool_call:
                        error_message += "No NewCode was provided in the tool call. Call the tool again but this time provide the NewCode.\n"
                    for _ in range(1): # this is super jank code but it works for now
                        section_letter = tool_call["sectionid"].strip()
                        section_id = excel_col_to_int(section_letter)
                        old_code = tool_call["originalcode"].strip("\n")
                        new_code = tool_call["newcode"].strip("\n")
                        if section_id >= len(chunks):
                            error_message = f"Could not find section {section_letter} in file {file_path}, which has {len(chunks)} sections."
                            break
                        elif section_id < 0:
                            error_message = f"The section ID {section_letter} can not be parsed."
                            break

                        # fetch the chunk of code we will be modifying
                        try:
                            chunk = chunks[section_id]
                        except Exception:
                            error_message = f"Could not fetch the chunk of code for section {section_letter} in file {file_path}. Make sure you are ONLY modifying the current file {file_path} and NOT a READ ONLY file."
                            break

                        # if the old_code couldn't be found in the chunk we need to let the llm know
                        if old_code not in chunk:
                            chunks_with_old_code = [
                                index
                                for index, chunk in enumerate(chunks)
                                if old_code in chunk
                            ]
                            chunks_with_old_code = chunks_with_old_code[:5]
                            error_message = f"The OriginalCode provided does not appear to be present in section {section_letter}. The OriginalCode contains:\n```\n{old_code}\n```\nBut section {section_letter} in {file_path} has code:\n```\n{chunk}\n```"
                            if chunks_with_old_code:
                                error_message += "\n\nDid you mean one of the following sections?"
                                error_message += "\n".join(
                                    [
                                        f'\n<section id="{int_to_excel_col(index + 1)}">\n{chunks[index]}\n</section>\n```'
                                        for index in chunks_with_old_code
                                    ]
                                )
                            else:
                                error_message += "\n\nMake another replacement. It seems there may be a spelling or indentation error as the OriginalCode could not be found in the code file. Consider missing or misplaced whitespace, comments or delimiters. Then, identify what should be the correct OriginalCode should be, and make another replacement with the corrected OriginalCode."
                            break
                        # apply changes
                        new_chunk = chunk.replace(old_code, new_code, 1)
                        if new_chunk == chunk:
                            logger.warning("No changes were made to the code.")
                        
                        new_chunks[section_id] = new_chunk
                        new_contents = current_contents.replace(
                            chunk, new_chunk, 1
                        )

                        # Check if changes were made
                        if new_contents == current_contents:
                            logger.warning("No changes were made to the code.")
                            error_message = "No changes were made, make sure old_code and new_code are not the same."
                            break
                        
                        # Check if the changes are valid
                        if not error_message:
                            check_results = get_check_results(file_path, new_contents)
                            check_results_message = check_results.is_worse_than_message(initial_check_results)
                            failing_parse = check_results.parse_error_message if not initial_check_results.parse_error_message else ""
                            current_diff = generate_diff(
                                current_contents, new_contents
                            )
                            if not failing_parse:
                                success_messages.append(
                                    f"The following changes have been applied:\n```diff\n{current_diff}\n```\nYou can continue to make changes to the code sections and call the SearchAndReplace tool again."
                                )
                                if check_results_message:
                                    warning_message = f"\n\nWARNING\n\n{check_results_message}"
                            else:
                                error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code.\nFirst, identify where the broken code occurs, why it is broken and what the correct change should be. Then, retry the SearchAndReplace with different changes that yield valid code."
                                break
                    if not error_message:
                        chunks = new_chunks
                    if error_message:
                        logger.error(f"Error occured in SearchAndReplace tool: {error_message}")
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n {error_message}"
                        )

                    if not error_message:
                        success_message = (
                            "SUCCESS\n\nThe following changes have been applied:\n\n"
                            + generate_diff(current_contents, new_contents)
                        ) + f"{warning_message}\n\nYou can continue to make changes to the code sections and call the SearchAndReplace tool again, or go back to searching for keywords using the KeywordSearch tool, which is great for finding all definitions or usages of a function or class."
                        # set contents
                        current_contents = new_contents

                        logger.info(success_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\n\n{success_message}"
                        )
                elif tool_name == "GetAdditionalContext":
                    error_message = ""
                    keyword = tool_call["keyword"].strip()
                    rg_command = ["rg", "-n", "-i" , keyword, cwd]
                    try:
                        result = subprocess.run(rg_command, text=True, capture_output=True)
                        output = result.stdout
                        if output:
                            # post process rip grep output to be more condensed
                            rg_output_pretty = post_process_rg_output(cwd, sweep_config, output)
                        else:
                            error_message = f"FAILURE: No results found for keyword: {keyword} in the entire codebase. Please try a new keyword. If you are searching for a function definition try again with different whitespaces."
                    except Exception as e:
                        logger.error(f"FAILURE: An Error occured while trying to find the keyword {keyword}: {e}")
                        error_message = f"FAILURE: An Error occured while trying to find the keyword {keyword}: {e}"
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
                    for key in ["justification", "keyword"]:
                        if key not in tool_call:
                            error_message = f"No {key} was provided in the KeywordSearch tool call. Call the tool again but this time provide the {key}."
                            break
                    
                    # if no issues continue with search
                    if not error_message:
                        keyword = tool_call["keyword"].strip()
                        match_indices = []
                        match_context_indices = []
                        relevant_file_match_indices: dict[str, list[int]] = defaultdict(
                            list
                        )
                        relevant_file_match_context_indices: dict[str, list[int]] = defaultdict(
                            list
                        )
                        # search current code file
                        for i, chunk in enumerate(chunks):
                            if keyword in chunk:
                                match_indices.append(i)
                                match_context_indices.append(max(0, i - 1))
                                match_context_indices.append(i)
                                match_context_indices.append(min(len(chunks) - 1, i + 1))
                        # search all relevant code files
                        for (
                            relevant_file_path,
                            relevant_file_chunk_group,
                        ) in relevant_file_chunks.items():
                            for i, chunk in enumerate(relevant_file_chunk_group):
                                if keyword in chunk:
                                    relevant_file_match_indices[
                                        relevant_file_path
                                    ].append(i)
                                    relevant_file_match_context_indices[
                                        relevant_file_path
                                    ].append(max(0, i - 1))
                                    relevant_file_match_context_indices[
                                        relevant_file_path
                                    ].append(i)
                                    relevant_file_match_context_indices[
                                        relevant_file_path
                                    ].append(
                                        min(len(relevant_file_chunk_group) - 1, i + 1)
                                    )

                        match_indices = sorted(list(set(match_indices)))
                        match_context_indices = sorted(list(set(match_context_indices)))
                        relevant_file_match_indices = {
                            k: sorted(list(set(v)))
                            for k, v in relevant_file_match_indices.items()
                        }
                        relevant_file_match_context_indices = {
                            k: sorted(list(set(v)))
                            for k, v in relevant_file_match_context_indices.items()
                        }
                        if not match_indices and not relevant_file_match_indices:
                            relevant_filepaths_string = ", ".join(relevant_filepaths)
                            error_message = f"The keyword {keyword} does not appear to be present in the CURRENT code file to modify: {file_path} and relevant READ ONLY code files: {relevant_filepaths_string}. Consider missing or misplaced whitespace, comments or delimiters."
                        else:
                            # for matches inside current code file
                            if match_indices:
                                sections_message = english_join(
                                    [
                                        int_to_excel_col(match_index + 1)
                                        for match_index in match_indices
                                    ]
                                )
                                starter_message = f"CURRENT FILE\n\nThe keyword {keyword} was found in sections {sections_message} of the CURRENT file {file_path}, which you MAY modify. They appear in the following places:\n\n"
                                success_message += (
                                    build_keyword_search_match_results(
                                        match_indices,
                                        chunks,
                                        keyword,
                                        starter_message,
                                        readonly=True
                                    )
                                )
                                if relevant_file_match_indices:
                                    success_message += "\n\n"
                            else:
                                success_message += f"The keyword {keyword} was not found in the current file. However, it was found in the following relevant READONLY file(s).\n\n"
                            # for matches inside relevant code files
                            if relevant_file_match_indices:
                                sections_message = english_join(
                                    [
                                        int_to_excel_col(match_index + 1)
                                        for match_index in match_indices
                                    ]
                                )
                                for (
                                    relevant_file_path,
                                    relevant_file_match_indices,
                                ), (
                                    _,
                                    relevant_file_match_context_indices,
                                ) in zip(relevant_file_match_indices.items(), relevant_file_match_context_indices.items()):
                                    sections_message = english_join(
                                        [
                                            int_to_excel_col(match_index + 1)
                                            for match_index in relevant_file_match_indices
                                        ]
                                    )
                                    also_keyword = "also " if match_indices else ""
                                    starter_message = f"READONLY FILES\n\nThe keyword {keyword} was {also_keyword}found in sections {sections_message} of the READONLY file {relevant_file_path}, which you MAY NOT modify. They appear in the following places:\n\n"
                                    success_message += (
                                        build_keyword_search_match_results(
                                            relevant_file_match_context_indices,
                                            relevant_file_chunks[relevant_file_path],
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
                elif tool_name == "view_sections":
                    error_message = ""
                    success_message = ""
                    if "section_ids" not in tool_call:
                        error_message = "No section_ids found in tool call."

                    if not isinstance(tool_call["section_ids"], list):
                        error_message = "section_ids should be a list."

                    if not len(tool_call["section_ids"]):
                        error_message = "section_ids should not be empty."

                    # get one section before and after each section
                    section_indices = set()
                    for section_id in tool_call["section_ids"]:
                        section_index = excel_col_to_int(section_id)
                        section_indices.update(
                            (
                                int_to_excel_col(max(1, section_index - 1)),
                                int_to_excel_col(min(len(chunks), section_index)),
                                int_to_excel_col(min(len(chunks), section_index + 1)),
                                int_to_excel_col(min(len(chunks), section_index + 2)),
                            )
                        )
                    section_indices = sorted(list(section_indices))
                    if not error_message:
                        success_message = "Here are the sections:" + "\n\n".join(
                            [
                                f"<section id='{section_id}'>\n{chunks[excel_col_to_int(section_id)]}\n</section>"
                                for section_id in section_indices
                            ]
                        )

                    if error_message:
                        logger.debug(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n{error_message}"
                        )
                    else:
                        logger.debug(success_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\n{success_message}\n\nMake additional view_sections or keyword_search calls to find other keywords or sections or continue to make changes by calling the search_and_replace function."
                        )
                else:
                    tool_name, tool_call = assistant_generator.send(
                        f"ERROR\nUnexpected tool name: {tool_name}"
                    )
            else:
                logger.error("Too many iterations.")
        except StopIteration:
            pass
        diff = generate_diff(file_contents, current_contents)
        if diff:
            logger.info("Changes made:\n\n" + diff)
        else:
            logger.warning("No changes were made.")
        if current_contents != file_contents:
            return current_contents
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


# # @file_cache(ignore_params=["file_path", "chat_logger"])
# def function_modify(
#     request: str,
#     file_path: str,
#     file_contents: str,
#     additional_messages: list[Message] = [],
#     chat_logger: ChatLogger | None = None,
#     assistant_id: str = None,
#     start_line: int = -1,
#     end_line: int = -1,
#     ticket_progress: TicketProgress | None = None,
#     assistant_conversation: AssistantConversation | None = None,
#     seed: int = None,
# ):
#     try:

#         def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
#             if assistant_conversation:
#                 assistant_conversation.update_from_ids(
#                     assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
#                 )
#             ticket_progress.save()

#         current_contents = file_contents
#         initial_code_valid, _ = check_code(file_path, current_contents)
#         initial_code_valid = initial_code_valid or (
#             "<<<<<<<" in current_contents and ">>>>>>>" in current_contents
#         )  # If there's a merge conflict, we still check that the final code is valid

#         original_snippets = chunk_code(current_contents, file_path, 700, 200)
#         file_contents_lines = current_contents.split("\n")
#         chunks = [
#             "\n".join(file_contents_lines[snippet.start : snippet.end])
#             for snippet in original_snippets
#         ]
#         code_sections = []  # TODO: do this for the new sections after modifications
#         current_code_section = ""
#         for i, chunk in enumerate(chunks):
#             section_display = chunk
#             if len(current_code_section) + len(section_display) > MAX_CHARS - 1000:
#                 code_sections_string = f"# Code\nFile path:{file_path}\n<code>\n```\n{current_code_section}\n```\n</code>\n"
#                 code_sections.append(code_sections_string)
#                 current_code_section = section_display
#             else:
#                 current_code_section += "\n" + section_display
#         code_sections.append(current_code_section)
#         code_sections_string = "\n".join(code_sections)
#         additional_messages += [
#             *reversed(
#                 [
#                     Message(
#                         role="user",
#                         content=code_section,
#                     )
#                     for code_section in code_sections
#                 ]
#             ),
#             Message(
#                 role="user",
#                 content=f"# Request\n{request}",
#             ),
#         ]
#         assistant_generator = openai_assistant_call(
#             request="",  # already present in additional_messages
#             instructions=instructions,
#             additional_messages=additional_messages,
#             chat_logger=chat_logger,
#             assistant_id=assistant_id,
#             save_ticket_progress=(
#                 save_ticket_progress if ticket_progress is not None else None
#             ),
#             assistant_name="Code Modification Function Assistant",
#             tools=[
#                 {"type": "code_interpreter"},
#                 {"type": "function", "function": search_and_replace_schema},
#                 {"type": "function", "function": keyword_search_schema},
#             ],
#         )

#         try:
#             tool_name, tool_call = assistant_generator.send(None)
#             for i in range(50):
#                 print(tool_name, json.dumps(tool_call, indent=2))
#                 if tool_name == "multi_tool_use.parallel":
#                     key_value_pairs = list(tool_call.items())
#                     if len(key_value_pairs) > 1:
#                         tool_name, tool_call = assistant_generator.send(
#                             f"ERROR\nOnly one tool call is allowed at a time."
#                         )
#                         continue
#                     key, value = list(tool_call.items())[0]
#                     tool_name = key
#                     tool_call = value
#                 if tool_name == "search_and_replace":
#                     error_message = ""
#                     success_message = ""
#                     new_contents = current_contents

#                     if "replaces_to_make" not in tool_call:
#                         error_message = "No replaces_to_make found in tool call."
#                     else:
#                         for index, replace_to_make in enumerate(
#                             tool_call["replaces_to_make"]
#                         ):
#                             for key in ["old_code", "new_code"]:
#                                 if key not in replace_to_make:
#                                     error_message = f"Missing {key} in replace_to_make."
#                                     break
#                                 if not isinstance(replace_to_make[key], str):
#                                     error_message = f"{key} should be a string."
#                                     break

#                             if error_message:
#                                 break

#                             old_code = replace_to_make["old_code"].strip("\n")
#                             new_code = replace_to_make["new_code"].strip("\n")

#                             if old_code not in new_contents:
#                                 error_message += f"\n\nThe old contents can not be found in the new_contents for replacement {index}. Make another replacement. In the analysis_and_identification, first identify the indentation or spelling error. Consider missing or misplaced whitespace, comments or delimiters. Then, identify what should be the correct old_code, and make another replacement with the corrected old_code."
#                                 break
#                             new_contents = new_contents.replace(old_code, new_code, 1)
#                             if new_contents == current_contents:
#                                 logger.warning("No changes were made to the code.")
#                     if not error_message and new_contents == current_contents:
#                         error_message = "No changes were made, make sure old_code and new_code are not the same."

#                     if not error_message:
#                         # If the initial code is invalid, we don't need to/can't check the new code
#                         is_valid, message = (
#                             (True, "")
#                             if not initial_code_valid
#                             else check_code(file_path, new_contents)
#                         )
#                         if is_valid:
#                             diff = generate_diff(current_contents, new_contents)
#                             current_contents = new_contents
#                             success_message = f"The following changes have been applied:\n```diff\n{diff}\n```\nYou can continue to make changes to the code sections and call the `search_and_replace` function again."
#                         else:
#                             diff = generate_diff(current_contents, new_contents)
#                             error_message = f"No changes have been applied. This is because when the following changes are applied:\n\n```diff\n{diff}\n```\n\nIt produces invalid code with the following error message:\n```\n{message}\n```\n\nPlease retry the search_and_replace with different changes that yield valid code."

#                     if error_message:
#                         logger.error(error_message)
#                         tool_name, tool_call = assistant_generator.send(
#                             f"ERROR\nNo changes were made due to the following error:\n\n{error_message}"
#                         )
#                     else:
#                         logger.info(success_message)
#                         tool_name, tool_call = assistant_generator.send(
#                             f"SUCCESS\nHere are the new code sections:\n\n{success_message}"
#                         )
#                 elif tool_name == "keyword_search":
#                     error_message = ""
#                     success_message = ""

#                     for key in ["justification", "keyword"]:
#                         if key not in tool_call:
#                             error_message = f"Missing {key} in keyword_search."
#                             break

#                     if not error_message:
#                         keyword = tool_call["keyword"]
#                         matches = []
#                         lines = current_contents.splitlines()
#                         for i, line in enumerate(lines):
#                             if keyword in line:
#                                 matches.append(i)
#                         if not matches:
#                             error_message = f"The keyword {keyword} does not appear to be present in the code. Consider missing or misplaced whitespace, comments or delimiters."
#                         else:
#                             success_message = (
#                                 "The keyword was found on the following lines:\n\n"
#                             )
#                         for line_number in matches:
#                             line = lines[line_number]
#                             col_of_keyword = max(
#                                 line.index(keyword) + len(str(line_number)) + 1, 0
#                             )
#                             match_display = (
#                                 f"{line_number}: {line}\n {' ' * col_of_keyword}^\n"
#                             )
#                             success_message += f"{match_display}"

#                     if error_message:
#                         logger.debug(error_message)
#                         tool_name, tool_call = assistant_generator.send(
#                             f"ERROR\nThe search failed due to the following error:\n\n{error_message}"
#                         )
#                     else:
#                         logger.debug(success_message)
#                         tool_name, tool_call = assistant_generator.send(
#                             f"SUCCESS\nHere are the lines containing the keywords:\n\n{success_message}"
#                         )
#                 else:
#                     assistant_generator.send(
#                         f"ERROR\nUnexpected tool name: {tool_name}"
#                     )
#         except StopIteration:
#             pass
#         diff = generate_diff(file_contents, current_contents)
#         if diff:
#             logger.info("Changes made:")
#             logger.info(diff[: min(1000, len(diff))])
#         if current_contents != file_contents:
#             return current_contents
#         logger.warning("No changes were made.")
#     except AssistantRaisedException as e:
#         logger.exception(e)
#         discord_log_error(
#             str(e)
#             + "\n\n"
#             + traceback.format_exc()
#             + "\n\n"
#             + str(chat_logger.data if chat_logger else "")
#             + "\n\n"
#             + str(ticket_progress.tracking_id if ticket_progress else "")
#         )
#     except Exception as e:
#         logger.exception(e)
#         # TODO: Discord
#         discord_log_error(
#             str(e)
#             + "\n\n"
#             + traceback.format_exc()
#             + "\n\n"
#             + str(chat_logger.data if chat_logger else "")
#             + "\n\n"
#             + str(ticket_progress.tracking_id if ticket_progress else "")
#         )
#         return None
#     return None
if not USE_ASSISTANT:
    logger.warning(
        "Using our own implementation to mock Assistant API as it is unstable (experimental)"
    )
    function_modify = function_modify_unstable  # noqa

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
        file_contents=file_contents,
        chat_logger=ChatLogger(
            {
                "username": "kevinlu1248",
                "title": request
            }
        ),
        additional_messages=additional_messages,
        ticket_progress=TicketProgress(tracking_id="test_remove_assistant_1"),
    )
