import json
import textwrap
import traceback

from loguru import logger

from sweepai.agents.assistant_functions import (
    chain_of_thought_schema,
    keyword_search_schema,
    search_and_replace_schema,
)
from sweepai.agents.assistant_wrapper import openai_assistant_call
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.diff import generate_diff
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.utils import check_code, chunk_code

# Pre-amble using ideas from https://github.com/paul-gauthier/aider/blob/main/aider/coders/udiff_prompts.py
# Doesn't regress on the benchmark but improves average code generated and avoids empty comments.
instructions = """You are an expert software developer and your job is to edit code to complete the user's request.
You are diligent and tireless and always COMPLETELY IMPLEMENT the needed code!
You NEVER leave comments describing code without implementing it!
Always use best practices when coding.
Respect and use existing conventions, libraries, etc that are already present in the code base.
Your job is to make edits to the file to complete the user "# Request".

# Instructions
1. Use the propose_problem_analysis_and_plan function to analyze the user's request and construct a plan of keywords to search for and the changes to make.
2. Use the keyword_search function to find the right places to make changes.
3. Use the search_and_replace function to make the changes.
    - Keep whitespace and comments.
    - Make the minimum necessary search_and_replaces to make changes to the snippets.
    - Write multiple small changes instead of a single large change.
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


MAX_CHARS = 32000
TOOLS_MAX_CHARS = 20000


# ensure that all additional_messages are 32768 characters at most, if not split them
def ensure_additional_messages_length(additional_messages: list[Message]):
    for i, additional_message in enumerate(additional_messages):
        if len(additional_message.content) > MAX_CHARS:
            new_messages = textwrap.wrap(additional_message.content, MAX_CHARS)
            # replace the original message with the broken up messages
            for j, new_message in enumerate(new_messages):
                if j == 0:
                    additional_messages[i] = Message(
                        role=additional_message.role,
                        content=new_message,
                    )
                else:
                    additional_messages.insert(
                        i + j,
                        Message(
                            role=additional_message.role,
                            content=new_message,
                        ),
                    )
    return additional_messages


# @file_cache(ignore_params=["file_path", "chat_logger"])
def function_modify(
    request: str,
    file_path: str,
    file_contents: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = None,
    start_line: int = -1,
    end_line: int = -1,
    ticket_progress: TicketProgress | None = None,
    assistant_conversation: AssistantConversation | None = None,
    seed: int = None,
):
    try:

        def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
            if assistant_conversation:
                assistant_conversation.update_from_ids(
                    assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
                )
            ticket_progress.save()

        current_contents = file_contents
        initial_code_valid, _ = check_code(file_path, current_contents)
        initial_code_valid = initial_code_valid or (
            "<<<<<<<" in current_contents and ">>>>>>>" in current_contents
        )

        original_snippets = chunk_code(current_contents, file_path, 700, 200)
        # original_snippets = chunk_code(current_contents, file_path, 1500, 200)
        file_contents_lines = current_contents.split("\n")
        chunks = [
            "\n".join(file_contents_lines[snippet.start : snippet.end])
            for snippet in original_snippets
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
        code_sections.append(current_code_section)
        code_sections_string = "\n".join(code_sections)
        additional_messages += [
            *reversed(
                [
                    Message(
                        role="user",
                        content=code_section,
                    )
                    for code_section in code_sections
                ]
            ),
            Message(
                role="user",
                content=f"# Request\n{request}",
            ),
        ]
        # make sure all additional messages are < 32k chars long
        additional_messages = ensure_additional_messages_length(additional_messages)
        assistant_generator = openai_assistant_call(
            request="",  # already present in additional_messages
            instructions=instructions,
            additional_messages=additional_messages,
            chat_logger=chat_logger,
            assistant_id=assistant_id,
            save_ticket_progress=(
                save_ticket_progress if ticket_progress is not None else None
            ),
            assistant_name="Code Modification Function Assistant",
            tools=[
                {"type": "function", "function": chain_of_thought_schema},
                {"type": "function", "function": keyword_search_schema},
                # {"type": "function", "function": view_sections_schema},
                {"type": "function", "function": search_and_replace_schema},
            ],
        )

        try:
            done_counter = 0
            tool_name, tool_call = assistant_generator.send(None)
            for i in range(10000):
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
                elif tool_name == "propose_problem_analysis_and_plan":
                    tool_name, tool_call = assistant_generator.send(
                        "SUCCESS\nSounds like a great plan! Let's start by using the keyword_search function to find the right places to make changes, and the search_and_replace function to make the changes."
                    )
                elif tool_name == "search_and_replace":
                    error_message = ""
                    success_message = ""
                    new_contents = current_contents
                    new_chunks = [chunk for chunk in chunks]  # deepcopy

                    if "replaces_to_make" not in tool_call:
                        error_message = "No replaces_to_make found in tool call."
                    elif len(tool_call["replaces_to_make"]) == 0:
                        error_message = "replace_to_make should not be empty."
                    else:
                        success_messages = []
                        for index, replace_to_make in enumerate(
                            tool_call["replaces_to_make"]
                        ):
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
                                is_valid, message = check_code(
                                    file_path, current_new_contents
                                )
                                current_diff = generate_diff(
                                    new_contents, current_new_contents
                                )
                                if is_valid:
                                    success_messages.append(
                                        f"The following changes have been applied:\n```diff\n{current_diff}\n```\nYou can continue to make changes to the code sections and call the `search_and_replace` function again."
                                    )
                                else:
                                    error_message = f"Error: Invalid code changes have been applied. You requested the following changes:\n\n```diff\n{current_diff}\n```\n\nBut it produces invalid code with the following error message:\n```\n{message}\n```\n\nFirst, identify where the broken Typescript code occurs, why it is broken and what the correct change should be. Then, retry the search_and_replace with different changes that yield valid code."
                                    break
                                new_contents = current_new_contents

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
                    #         error_message = f"No changes have been applied becuase invalid code changes have been applied. You requested the following changes:\n\n```diff\n{diff}\n```\n\nBut it produces invalid code with the following error message:\n```\n{message}\n```\n\nFirst, identify where the broken Typescript code occurs, why it is broken and what the correct change should be. Then, retry the search_and_replace with different changes that yield valid code."
                    if not error_message:
                        success_message = (
                            "The following changes have been applied:\n\n"
                            + generate_diff(current_contents, new_contents)
                        )
                        current_contents = new_contents

                    if error_message:
                        logger.error(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            "ERROR\n\n"
                            + "\n".join(
                                f"{i}th replace to make:\n\n{message}"
                                for i, message in enumerate(success_messages)
                            )
                            + f"\n{index}th replace to make: "
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
                        keyword = tool_call["keyword"]
                        match_indices = []
                        for i, chunk in enumerate(chunks):
                            if keyword in chunk:
                                match_indices.append(max(0, i - 1))
                                match_indices.append(i)
                                match_indices.append(min(len(chunks) - 1, i + 1))
                        match_indices = sorted(list(set(match_indices)))
                        if not match_indices:
                            error_message = f"The keyword {keyword} does not appear to be present in the code. Consider missing or misplaced whitespace, comments or delimiters."
                        else:
                            success_message = f"The keyword {keyword} was found in the following sections:\n\n"
                        for match_index in match_indices:
                            # TODO: handle multiple matches in one line
                            match = chunks[match_index]
                            match_lines = match.split("\n")
                            lines_containing_keyword = [
                                i
                                for i, line in enumerate(match_lines)
                                if keyword in line
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
                                        + " "
                                        * (
                                            cols_of_keyword[
                                                lines_containing_keyword.index(i)
                                            ]
                                        )
                                        + "^\n"
                                    )
                                else:
                                    match_display += f"{line}\n"
                            match_display = match_display.strip("\n")
                            success_message += f"<section id='{int_to_excel_col(match_index + 1)}'> ({len(lines_containing_keyword)} matches)\n{match_display}\n</section>\n"

                    if error_message:
                        logger.debug(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\n\n{error_message}"
                        )
                    else:
                        logger.debug(success_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\n{success_message}\n\nMake additional keyword_search calls to find other keywords or start making changes by calling the search_and_replace function."
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
                        import pdb

                        pdb.set_trace()
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


if __name__ == "__main__":
    request = "Convert any all logger.errors to logger.exceptions in api.py"
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
                "title": "Convert any all logger.errors to logger.exceptions in on_ticket.py",
            }
        ),
        # additional_messages=additional_messages,
        ticket_progress=TicketProgress(tracking_id="test_remove_assistant_1"),
    )
