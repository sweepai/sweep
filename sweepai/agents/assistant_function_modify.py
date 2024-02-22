import json
import traceback

from loguru import logger

from sweepai.agents.assistant_functions import (
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
instructions = """You are an expert software developer assigned to write code to complete the user's request.
You are diligent and tireless and always COMPLETELY IMPLEMENT the needed code!
You NEVER leave comments describing code without implementing it!
Always use best practices when coding.
Respect and use existing conventions, libraries, etc that are already present in the code base.
Your job is to make edits to the file to complete the user "# Request".

# Instructions
Modify the snippets above according to the request by calling the search_and_replace function.
* Keep whitespace and comments.
* Make the minimum necessary search_and_replaces to make changes to the snippets. Only write diffs for lines that have been asked to be changed.
* Write multiple small changes instead of a single large change."""


def int_to_excel_col(n):
    result = ""
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
        )  # If there's a merge conflict, we still check that the final code is valid

        original_snippets = chunk_code(current_contents, file_path, 700, 200)
        file_contents_lines = current_contents.split("\n")
        chunks = [
            "\n".join(file_contents_lines[snippet.start : snippet.end])
            for snippet in original_snippets
        ]
        code_sections = []  # TODO: do this for the new sections after modifications
        current_code_section = ""
        for i, chunk in enumerate(chunks):
            section_display = chunk
            if len(current_code_section) + len(section_display) > MAX_CHARS - 1000:
                code_sections_string = f"# Code\nFile path:{file_path}\n<code>\n```\n{current_code_section}\n```\n</code>\n"
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
                {"type": "code_interpreter"},
                {"type": "function", "function": search_and_replace_schema},
                {"type": "function", "function": keyword_search_schema},
            ],
        )

        try:
            tool_name, tool_call = assistant_generator.send(None)
            for i in range(50):
                print(tool_name, json.dumps(tool_call, indent=2))
                if tool_name == "multi_tool_use.parallel":
                    key_value_pairs = list(tool_call.items())
                    if len(key_value_pairs) > 1:
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\nOnly one tool call is allowed at a time."
                        )
                        continue
                    key, value = list(tool_call.items())[0]
                    tool_name = key
                    tool_call = value
                if tool_name == "search_and_replace":
                    error_message = ""
                    success_message = ""
                    new_contents = current_contents

                    if "replaces_to_make" not in tool_call:
                        error_message = "No replaces_to_make found in tool call."
                    else:
                        for index, replace_to_make in enumerate(
                            tool_call["replaces_to_make"]
                        ):
                            for key in ["old_code", "new_code"]:
                                if key not in replace_to_make:
                                    error_message = f"Missing {key} in replace_to_make."
                                    break
                                if not isinstance(replace_to_make[key], str):
                                    error_message = f"{key} should be a string."
                                    break

                            if error_message:
                                break

                            old_code = replace_to_make["old_code"].strip("\n")
                            new_code = replace_to_make["new_code"].strip("\n")

                            if old_code not in new_contents:
                                error_message += f"\n\nThe old contents can not be found in the new_contents for replacement {index}. Make another replacement. In the analysis_and_identification, first identify the indentation or spelling error. Consider missing or misplaced whitespace, comments or delimiters. Then, identify what should be the correct old_code, and make another replacement with the corrected old_code."
                                break
                            new_contents = new_contents.replace(old_code, new_code, 1)
                            if new_contents == current_contents:
                                logger.warning("No changes were made to the code.")
                    if not error_message and new_contents == current_contents:
                        error_message = "No changes were made, make sure old_code and new_code are not the same."

                    if not error_message:
                        # If the initial code is invalid, we don't need to/can't check the new code
                        is_valid, message = (
                            (True, "")
                            if not initial_code_valid
                            else check_code(file_path, new_contents)
                        )
                        if is_valid:
                            diff = generate_diff(current_contents, new_contents)
                            current_contents = new_contents
                            success_message = f"The following changes have been applied:\n```diff\n{diff}\n```\nYou can continue to make changes to the code sections and call the `search_and_replace` function again."
                        else:
                            diff = generate_diff(current_contents, new_contents)
                            error_message = f"No changes have been applied. This is because when the following changes are applied:\n\n```diff\n{diff}\n```\n\nIt produces invalid code with the following error message:\n```\n{message}\n```\n\nPlease retry the search_and_replace with different changes that yield valid code."

                    if error_message:
                        logger.error(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\nNo changes were made due to the following error:\n\n{error_message}"
                        )
                    else:
                        logger.info(success_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\nHere are the new code sections:\n\n{success_message}"
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
                        matches = []
                        lines = current_contents.splitlines()
                        for i, line in enumerate(lines):
                            if keyword in line:
                                matches.append(i)
                        if not matches:
                            error_message = f"The keyword {keyword} does not appear to be present in the code. Consider missing or misplaced whitespace, comments or delimiters."
                        else:
                            success_message = (
                                "The keyword was found on the following lines:\n\n"
                            )
                        for line_number in matches:
                            line = lines[line_number]
                            col_of_keyword = max(
                                line.index(keyword) + len(str(line_number)) + 1, 0
                            )
                            match_display = (
                                f"{line_number}: {line}\n {' ' * col_of_keyword}^\n"
                            )
                            success_message += f"{match_display}"

                    if error_message:
                        logger.debug(error_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"ERROR\nThe search failed due to the following error:\n\n{error_message}"
                        )
                    else:
                        logger.debug(success_message)
                        tool_name, tool_call = assistant_generator.send(
                            f"SUCCESS\nHere are the lines containing the keywords:\n\n{success_message}"
                        )
                else:
                    assistant_generator.send(
                        f"ERROR\nUnexpected tool name: {tool_name}"
                    )
        except StopIteration:
            pass
        diff = generate_diff(file_contents, current_contents)
        if diff:
            logger.info("Changes made:")
            logger.info(diff[: min(1000, len(diff))])
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
    )
