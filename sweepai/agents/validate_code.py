from __future__ import annotations

import difflib

from loguru import logger

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Message, RegexMatchableBaseModel
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.diff import sliding_window_replacement
from sweepai.utils.regex_utils import xml_pattern
from sweepai.utils.search_and_replace import match_indent

validate_changes_system_prompt = """\
You are a brilliant and meticulous senior engineer assigned to double-check code that was written by a junior engineer to complete the user's request. When you write code, the code works on the first try, is syntactically perfect, and is complete.

You are given diff hunks and the newly written code after the diff hunks have been applied. Check whether the final code valid. Then check if the user's request was met. Finally, list the ID's of diff hunks to revert.

Respond in the following format:

<analysis>
Determine whether the new_code is valid.
Determine whether the user's request was met.
Then for each diff hunk, determine whether it was helpful or whether it should be reverted.
Maximize information density.
</analysis>

<additional_changes required="yes or no">
Instructions for changes to make (if required)
Maximize information density.
</additional_changes>

<diffs_to_revert>
A
B
...
</diffs_to_revert>"""

hunk_format = """<hunk id="{id}">
{diff}
</hunk>"""

validate_changes_prompt = """\
# Code

File path: {file_path}

<new_code>
{new_code}
</new_code>

<diffs>
{diffs}
</diffs>

# User's Request
{request}

# Instructions
You are given diff hunks and the newly written code after the diff hunks have been applied. Check whether the final code valid. Then check if the user's request was met. Finally, list the ID's of diff hunks to revert.

Respond in the following format:

<analysis>
Determine whether the new_code is valid.
Determine whether the user's request was met.
Then for each diff hunk, determine whether it was helpful or whether it should be reverted.
Maximize information density.
</analysis>

<additional_changes required="yes or no">
Instructions for changes to make (if required)
Maximize information density.
</additional_changes>

<diffs_to_revert>
A
B
...
</diffs_to_revert>"""

alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def generate_diff(str1, str2):
    d = difflib.Differ()
    diff = d.compare(str1.splitlines(), str2.splitlines())
    return "\n".join(diff)


def git_conflict_format(diff_str):
    lines = diff_str.split("\n")
    output = []
    state = "neutral"

    UPDATED_MARKER = ">>>>>>> UPDATED"
    ORIGINAL_MARKER = "<<<<<<< ORIGINAL"
    SEPARATOR_MARKER = "======="

    for line in lines:
        if line.startswith("  "):
            if state == "add":
                output.append(UPDATED_MARKER)
            elif state == "del":
                output.extend([SEPARATOR_MARKER, UPDATED_MARKER])
            output.append(line[2:])
            state = "neutral"
        elif line.startswith("- "):
            if state == "neutral":
                output.append(ORIGINAL_MARKER)
            elif state == "add":
                output.extend([UPDATED_MARKER, ORIGINAL_MARKER])
            output.append(line[2:])
            state = "del"
        elif line.startswith("+ "):
            if state == "del":
                output.append(SEPARATOR_MARKER)
            elif state == "neutral":
                output.extend([ORIGINAL_MARKER, SEPARATOR_MARKER])
            output.append(line[2:])
            state = "add"

    if state == "add":
        output.append(UPDATED_MARKER)
    elif state == "del":
        output.extend([SEPARATOR_MARKER, UPDATED_MARKER])

    return "\n".join(output)


class ChangeValidation(RegexMatchableBaseModel):
    analysis: str
    additional_changes: str
    additional_changes_required_raw: str
    diffs_to_revert_raw: str
    _regex: str = "\s*".join(
        (
            xml_pattern("analysis"),
            xml_pattern(
                "additional_changes", required="additional_changes_required_raw"
            ),
            xml_pattern("diffs_to_revert", name="diffs_to_revert_raw"),
        )
    )

    @property
    def diffs_to_revert(self):
        return self.diffs_to_revert_raw.splitlines()

    @property
    def additional_changes_required(self):
        return self.additional_changes_required_raw.lower() == "yes"


class ChangeValidator(ChatGPT):
    old_code: str
    file_change_request: FileChangeRequest
    selected_snippets: list[str]
    updated_snippets: dict[int, str]
    additional_messages: list[str] = []

    @classmethod
    def create(
        cls,
        old_code: str,
        file_change_request: FileChangeRequest,
        selected_snippets: list[str],
        updated_snippets: dict[int, str],
        chat_logger: ChatLogger,
        additional_messages: list[Message] = [],
    ) -> ChangeValidation:
        obj = cls.from_system_message_string(
            validate_changes_system_prompt,
            old_code=old_code,
            file_change_request=file_change_request,
            selected_snippets=selected_snippets,
            updated_snippets=updated_snippets,
            chat_logger=chat_logger,
        )
        obj.messages.extend(additional_messages)
        return obj

    def create_new_file(self) -> str:
        result = self.old_code
        for idx, search in enumerate(self.selected_snippets):
            if idx not in self.updated_snippets:
                continue
            replace = self.updated_snippets[self.selected_snippets.index(search)]
            result, _, _ = sliding_window_replacement(
                result.splitlines(),
                search.splitlines(),
                match_indent(replace, search).splitlines(),
            )
            result = "\n".join(result)
        return result

    @staticmethod
    def make_hunk(old_code: str, new_code: str, id_: str):
        diff = git_conflict_format(generate_diff(old_code, new_code))
        return hunk_format.format(diff="\n".join(diff), id=id_)

    def generate_diffs(self):
        hunks: list[str] = []
        for idx, search in enumerate(self.selected_snippets):
            if idx not in self.updated_snippets:
                continue
            replace = self.updated_snippets[self.selected_snippets.index(search)]
            hunks.append(ChangeValidator.make_hunk(search, replace, alphabet[idx]))
        return "\n".join(hunks)

    def validate_changes(self):
        new_code = self.create_new_file()
        diffs = self.generate_diffs()
        change_validation_raw = self.chat(
            validate_changes_prompt.format(
                file_path=self.file_change_request.filename,
                diffs=diffs,
                new_code=new_code,
                request=self.file_change_request.instructions,
            )
        )
        change_validation = ChangeValidation.from_string(change_validation_raw)
        return change_validation

    def apply_validated_changes(self, change_validation: ChangeValidation):
        if change_validation.additional_changes_required:
            for diff in change_validation.diffs_to_revert:
                if diff not in alphabet:
                    logger.warning(f"Invalid diff ID: {diff}")
                    continue
                idx = alphabet.index(diff)
                del self.updated_snippets[idx]
        new_code = self.create_new_file()
        return new_code


if __name__ == "__main__":
    change_validation = ChangeValidation.from_string(
        """
<analysis>
The new code is syntactically valid. However, the user's request has not been fully met. The health_check function and related imports have been removed from api.py, but the import statement for the health_check function from health.py is missing.

Regarding the diff hunks:
- Hunk A: This hunk correctly removes the import of psutil, which is no longer needed in api.py.
- Hunk B: This hunk correctly removes the import of redis and JSONResponse, which are no longer needed in api.py.
- Hunk C: This hunk correctly removes the import of IS_SELF_HOSTED, MONGODB_URI, REDIS_URL, and SANDBOX_URL, which are no longer needed in api.py.
- Hunk D: This hunk correctly removes the check_sandbox_health function, but it leaves an empty try-except block which is not good practice.
- Hunk E: This hunk correctly removes the check_mongodb_health, check_redis_health, and health_check functions from api.py.
</analysis>

<additional_changes required="yes">
The import statement for the health_check function from health.py needs to be added to api.py. Also, the empty try-except block in the check_sandbox_health function should be removed or filled with appropriate code.
</additional_changes>

<diffs_to_revert>
D
</diffs_to_revert>
"""
    )
    # print(change_validation)
    # print(change_validation.diffs_to_revert)
    old_code = """\
import ctypes
import threading

import redis
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
from pymongo import MongoClient
"""
    selected_snippets = ["from fastapi.responses import HTMLResponse, JSONResponse"]
    updated_snippets = {0: "from fastapi.responses import HTMLRes"}
    instructions = """\
• Remove the health_check function as it has been moved to health.py.
• Remove the following imports as they are no longer needed in api.py:
  - import psutil
  - import redis
  - from fastapi.responses import JSONResponse
  - from sweepai.config.server import IS_SELF_HOSTED, MONGODB_URI, REDIS_URL, SANDBOX_URL
• Add an import statement for the health_check function from health.py."""
    file_change_request = FileChangeRequest(
        filename="api.py",
        instructions=instructions,
        change_type="modify",
    )
    change_validator = ChangeValidator.create(
        old_code,
        file_change_request=file_change_request,
        selected_snippets=selected_snippets,
        updated_snippets=updated_snippets,
        chat_logger=ChatLogger(mock=True),
    )
    change_validation = change_validator.validate_changes()
    new_code = change_validator.apply_validated_changes(change_validation)
    assert old_code == new_code
