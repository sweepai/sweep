# sweepai/handlers/on_comment.py
import traceback
import re

import modal
from github.ContentFile import ContentFile
from github.GithubException import GithubException
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel

from sweepai.core.chat import ChatGPT
from sweepai.core.code_repair import CodeRepairer
from sweepai.core.edit_chunk import EditBot
from sweepai.core.entities import (
    FileCreation,
    FileChangeRequest,
    FilesToChange,
    PullRequest,
    RegexMatchError,
    Function,
    Snippet, NoFilesException, Message
)
from sweepai.core.prompts import (
    files_to_change_prompt,
    pull_request_prompt,
    create_file_prompt,
    modify_file_prompt_2,
    modify_file_prompt_3,
    snippet_replacement,
    chunking_prompt,
)
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.config.server import DB_MODAL_INST_NAME, SECONDARY_MODEL
from sweepai.utils.diff import diff_contains_dups_or_removals, format_contents, generate_diff, generate_new_file, generate_new_file_from_patch, is_markdown

USING_DIFF = True

class MaxTokensExceeded(Exception):
    def __init__(self, filename):
        self.filename = filename

class CodeGenBot(ChatGPT):
    def summarize_snippets(self, create_thoughts, modify_thoughts):
        snippet_summarization = self.chat(
            snippet_replacement.format(
                thoughts=create_thoughts + "\n" + modify_thoughts
            ),
            message_key="snippet_summarization",
        )

        # Delete excessive tokens
        self.delete_messages_from_chat("relevant_snippets")
        self.delete_messages_from_chat("relevant_directories")
        self.delete_messages_from_chat("relevant_tree")

        # Delete past instructions
        self.delete_messages_from_chat("files_to_change", delete_assistant=False)

        # Delete summarization instructions
        self.delete_messages_from_chat("snippet_summarization")

        msg = Message(content=snippet_summarization, role="assistant", key="bot_analysis_summary")
        self.messages.insert(-2, msg)
        pass

    def get_files_to_change(self, retries=2):
        file_change_requests: list[FileChangeRequest] = []
        # Todo: put retries into a constants file
        # also, this retries multiple times as the calls for this function are in a for loop

        for count in range(retries):
            try:
                logger.info(f"Generating for the {count}th time...")
                files_to_change_response = self.chat(files_to_change_prompt,
                                                     message_key="files_to_change")  # Dedup files to change here
                files_to_change = FilesToChange.from_string(files_to_change_response)
                create_thoughts = files_to_change.files_to_create.strip()
                modify_thoughts = files_to_change.files_to_modify.strip()

                files_to_create: list[str] = files_to_change.files_to_create.split("\n*")
                files_to_modify: list[str] = files_to_change.files_to_modify.split("\n*")
                for file_change_request, change_type in zip(
                        files_to_create + files_to_modify,
                        ["create"] * len(files_to_create)
                        + ["modify"] * len(files_to_modify),
                ):
                    file_change_request = file_change_request.strip()
                    if not file_change_request or file_change_request == "* None":
                        continue
                    logger.debug(file_change_request)
                    logger.debug(change_type)
                    file_change_requests.append(
                        FileChangeRequest.from_string(
                            file_change_request, change_type=change_type
                        )
                    )
                # Create a dictionary to hold file names and their corresponding instructions
                file_instructions_dict = {}
                for file_change_request in file_change_requests:
                    # If the file name is already in the dictionary, append the new instructions
                    if file_change_request.filename in file_instructions_dict:
                        instructions, change_type = file_instructions_dict[file_change_request.filename]
                        file_instructions_dict[file_change_request.filename] = (
                            instructions + " " + file_change_request.instructions, change_type)
                    else:
                        file_instructions_dict[file_change_request.filename] = (
                            file_change_request.instructions, file_change_request.change_type)
                file_change_requests = [
                    FileChangeRequest(filename=file_name, instructions=instructions, change_type=change_type) for
                    file_name, (instructions, change_type) in file_instructions_dict.items()]
                if file_change_requests:
                    return file_change_requests, create_thoughts, modify_thoughts
            except RegexMatchError:
                logger.warning("Failed to parse! Retrying...")
                self.delete_messages_from_chat("files_to_change")
                continue
        raise NoFilesException()
        \ No newline at end of file
        \n

