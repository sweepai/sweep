from __future__ import annotations

import os
import re
import string
import uuid
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any, ClassVar, Literal, Type, TypeVar
from urllib.parse import quote

from loguru import logger
from pydantic import BaseModel, Field

from sweepai.utils.str_utils import (
    blockquote,
    clean_logs,
    create_collapsible,
    format_sandbox_success,
)

Self = TypeVar("Self", bound="RegexMatchableBaseModel")


class Message(BaseModel):
    role: Literal["system"] | Literal["user"] | Literal["assistant"] | Literal[
        "function"
    ]
    content: str | None = None
    name: str | None = None
    function_call: dict | None = None
    key: str | None = None

    @classmethod
    def from_tuple(cls, tup: tuple[str | None, str | None]) -> Self:
        if tup[0] is None:
            return cls(role="assistant", content=tup[1])
        else:
            return cls(role="user", content=tup[0])

    def to_openai(self) -> str:
        obj = {
            "role": self.role,
            "content": self.content,
        }
        if self.function_call:
            obj["function_call"] = self.function_call
        if self.role == "function":
            obj["name"] = self.name
        return obj


class Function(BaseModel):
    class Parameters(BaseModel):
        type: str = "object"
        properties: dict

    name: str
    description: str
    parameters: Parameters


class RegexMatchError(ValueError):
    pass


class RegexMatchableBaseModel(BaseModel):
    _regex: ClassVar[str]

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        # match = re.search(file_regex, string, re.DOTALL)
        match = re.search(cls._regex, string, re.DOTALL)
        if match is None:
            logger.warning(f"Did not match {string} with pattern {cls._regex}")
            raise RegexMatchError("Did not match")
        return cls(
            **{k: (v if v else "").strip("\n") for k, v in match.groupdict().items()},
            **kwargs,
        )


class ExpandedPlan(RegexMatchableBaseModel):
    queries: str
    additional_instructions: str

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        query_pattern = r"""<queries>(\n)?(?P<queries>.*)</queries>"""
        query_match = re.search(query_pattern, string, re.DOTALL)
        instructions_pattern = r"""<additional_instructions>(\n)?(?P<additional_instructions>.*)</additional_instructions>"""
        instructions_match = re.search(instructions_pattern, string, re.DOTALL)
        return cls(
            queries=query_match.groupdict()["queries"] if query_match else None,
            additional_instructions=instructions_match.groupdict()[
                "additional_instructions"
            ].strip()
            if instructions_match
            else "",
        )


# todo (fix double colon regex): Update the split from "file_tree.py : desc" to "file_tree.py\tdesc"
# tab supremacy
def clean_filename(file_name: str):
    valid_chars = "-_./$[]%s%s" % (string.ascii_letters, string.digits)
    file_name = "".join(c for c in file_name if c in valid_chars)
    file_name = file_name.replace(" ", "")
    file_name = file_name.strip("`")
    return os.path.normpath(file_name)


def clean_instructions(instructions: str):
    return instructions.strip()


def create_error_logs(
    commit_url_display: str,
    sandbox_response: SandboxResponse,
    file_path: str = "",
):
    return (
        create_collapsible(
            f"Sandbox logs for {commit_url_display}",
            blockquote(
                "\n\n".join(
                    [
                        create_collapsible(
                            f"<code>{output}</code> {i + 1}/{len(sandbox_response.outputs)} {format_sandbox_success(sandbox_response.success)}",
                            f"<pre>{clean_logs(output)}</pre>",
                            i == len(sandbox_response.outputs) - 1,
                        )
                        for i, output in enumerate(sandbox_response.outputs)
                        if len(sandbox_response.outputs) > 0
                    ]
                )
            ),
            opened=True,
        )
        if sandbox_response
        else ""
    )


class ExtractionRequest(RegexMatchableBaseModel):
    use_tools: bool
    _regex = r"""<use_tools>\s+(?P<use_tools>.*?)</use_tools>"""

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        use_tools_pattern = r"""<use_tools>\s+(?P<use_tools>.*?)</use_tools>"""
        use_tools_match = re.search(use_tools_pattern, string, re.DOTALL)
        use_tools = use_tools_match.groupdict()["use_tools"].strip().lower() == "true"
        return cls(use_tools=use_tools)


class FileChangeRequest(RegexMatchableBaseModel):
    filename: str
    instructions: str
    change_type: Literal["modify"] | Literal["create"] | Literal["delete"] | Literal[
        "rename"
    ] | Literal["rewrite"] | Literal["check"] | Literal["refactor"] | Literal["test"]
    _regex = r"""<(?P<change_type>[a-z_]+)\s+file=\"(?P<filename>[a-zA-Z0-9/\\\.\[\]\(\)\_\+\- @]*?)\"( start_line=\"(?P<start_line>.*?)\")?( end_line=\"(?P<end_line>.*?)\")?( entity=\"(.*?)\")?( source_file=\"(?P<source_file>.*?)\")?( destination_module=\"(?P<destination_module>.*?)\")?( relevant_files=\"(?P<raw_relevant_files>.*?)\")?(.*?)>(?P<instructions>.*?)\s*<\/\1>"""
    entity: str | None = None
    source_file: str | None = None
    old_content: str | None = None
    new_content: str | None = None
    raw_relevant_files: str | None = None
    start_line: int | str | None = None
    end_line: int | str | None = None
    start_and_end_lines: list[tuple] = []
    comment_line: int | None = None
    sandbox_response: None = None
    failed_sandbox_test: bool | None = False
    parent: FileChangeRequest | None = None
    status: Literal["succeeded"] | Literal["failed"] | Literal["queued"] | Literal[
        "running"
    ] = "queued"
    destination_module: str | None = None
    commit_hash_url: str | None = None
    id_: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def get_edit_url(self, repo_full_name: str, branch_name: str):
        url = f"https://github.com/{repo_full_name}/edit/{branch_name}/{self.filename}"
        if self.start_line and self.end_line:
            url += f"#L{self.start_line}-L{self.end_line}"
        return url

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        result = super().from_string(string, **kwargs)
        result.filename = result.filename.strip("/")
        result.instructions = result.instructions.replace("\n*", "\n•")
        if result.source_file:
            result.source_file = result.source_file.strip()
            if " " in result.source_file:
                result.source_file = result.source_file.split(" ")[0]
        if result.instructions.startswith("*"):
            result.instructions = "•" + result.instructions[1:]
        if result.start_line:
            try:
                result.start_line = int(result.start_line)
            except ValueError:
                result.start_line = None
        if result.end_line:
            try:
                result.end_line = int(result.end_line)
            except ValueError:
                result.start_line = None
        return result

    @property
    def relevant_files(self):
        if not self.raw_relevant_files:
            return []

        return [
            relevant_file
            for relevant_file in self.raw_relevant_files.split(" ")
            if relevant_file != self.filename
        ]

    @property
    def entity_display(self):
        if self.entity:
            return f"`{self.filename}:{self.entity}`"
        else:
            return f"`{self.filename}`"

    @property
    def status_display(self):
        if self.status == "succeeded":
            return "✓"
        elif self.status == "failed":
            if self.change_type == "modify":
                return "! No changes made"
            return "✗"
        elif self.status == "queued":
            return "▶"
        elif self.status == "running":
            return "⋯"
        else:
            raise ValueError(f"Unknown status {self.status}")

    @property
    def display_summary(self):
        if self.change_type == "check":
            return f"Running GitHub Actions for `{self.filename}`"
        return f"{self.change_type.capitalize()} `{self.filename}`"

    @property
    def summary(self):
        prefix = {"failed": "✗", "succeeded": "✓", "queued": "▶", "running": "⋯"}[
            self.status
        ] + " "
        if self.change_type == "check":
            return prefix + f"Run GitHub Actions for `{self.filename}`"
        return prefix + f"{self.change_type.capitalize()}\n{self.filename}"

    @property
    def color(self):
        color_map = {
            "failed": "red2",
            "succeeded": "#0ee832",
            "queued": "white",
            "running": "yellow",
        }
        return color_map[self.status]

    @property
    def entity_display_without_backtick(self):
        if self.entity:
            return f"{self.filename}:{self.entity}"
        else:
            return f"{self.filename}"

    @property
    def instructions_ticket_display(self):
        return self.instructions_display

    @property
    def instructions_display(self):
        # if self.change_type == "check":
        #     return f"Run GitHub Actions for `{self.filename}` with results:\n{self.instructions}"
        return f"{self.change_type.capitalize()} {self.filename} with contents:\n{self.instructions}"

    @property
    def diff_display(self):
        if self.old_content and self.new_content:
            diff = unified_diff(
                self.old_content.splitlines(keepends=True),
                self.new_content.splitlines(keepends=True),
            )
            diff_text = "".join(diff)
            return f"<pre>{diff_text}</pre>"
        return ""


class FileCreation(RegexMatchableBaseModel):
    commit_message: str
    code: str
    _regex = r"""<new_file(.*?)>(?P<code>.*)</new_file>"""
    # Regex updated to support ``` outside of <new_file> tags

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        re_match = re.search(cls._regex, string, re.DOTALL)

        if re_match is None:
            logger.info(f"Did not match {string} with pattern {cls._regex}")
            raise ValueError("No <new_file> tags or ``` found in code block")

        result = cls(
            code=re_match.groupdict()["code"].strip(),
            commit_message="Created file",
        )

        first_index = result.code.find("<new_file>")
        if first_index >= 0:
            last_index = result.code.rfind("</new_file>")
            result.code = result.code[first_index + len("<new_file>") : last_index]
        else:
            first_index = result.code.find("```")
            if first_index >= 0:
                last_index = result.code.rfind("```")
                file_extension = os.path.splitext(result.code)[1]
                if file_extension not in [".md", ".rst", ".mdx", ".txt"]:
                    result.code = result.code[first_index:last_index]

        result.code = result.code.strip()
        if result.code.endswith("</new_file>"):
            result.code = result.code[: -len("</new_file>")]
            result.code = result.code.strip()

        # Todo: Remove this?
        if len(result.code) == 1:
            result.code = result.code.replace("```", "")
            return result.code + "\n"

        if result.code.startswith("```"):
            first_newline = result.code.find("\n")
            result.code = result.code[first_newline + 1 :]

        result.code = result.code.strip()
        if result.code.endswith("```"):
            result.code = result.code[: -len("```")]
            result.code = result.code.strip()
        result.code += "\n"
        return result


class PullRequest(RegexMatchableBaseModel):
    title: str
    branch_name: str
    content: str
    _regex = r'''pr_title\s+=\s+"(?P<title>.*?)"\n+branch\s+=\s+"(?P<branch_name>.*?)"\n+pr_content\s+=\s+f?"""(?P<content>.*?)"""'''


class ProposedIssue(RegexMatchableBaseModel):
    title: str
    body: str
    issue_id: int | None = None
    _regex = r'<issue\s+title="(?P<title>.*?)">(?P<body>.*?)</issue>'


class Snippet(BaseModel):
    """
    Start and end refer to line numbers
    """

    content: str
    start: int
    end: int
    file_path: str

    def __eq__(self, other):
        if isinstance(other, Snippet):
            return (
                self.file_path == other.file_path
                and self.start == other.start
                and self.end == other.end
            )
        return False

    def __hash__(self):
        return hash((self.file_path, self.start, self.end))

    def get_snippet(self, add_ellipsis: bool = True, add_lines: bool = True):
        lines = self.content.splitlines()
        snippet = "\n".join(
            (f"{i + self.start}: {line}" if add_lines else line)
            for i, line in enumerate(lines[max(self.start - 1, 0) : self.end])
        )
        if add_ellipsis:
            if self.start > 1:
                snippet = "...\n" + snippet
            if self.end < self.content.count("\n") + 1:
                snippet = snippet + "\n..."
        return snippet

    def __add__(self, other):
        assert self.content == other.content
        assert self.file_path == other.file_path
        return Snippet(
            content=self.content,
            start=self.start,
            end=other.end,
            file_path=self.file_path,
        )

    def __xor__(self, other: "Snippet") -> bool:
        """
        Returns True if there is an overlap between two snippets.
        """
        if self.file_path != other.file_path:
            return False
        return self.file_path == other.file_path and (
            (self.start <= other.start and self.end >= other.start)
            or (other.start <= self.start and other.end >= self.start)
        )

    def __or__(self, other: "Snippet") -> "Snippet":
        assert self.file_path == other.file_path
        return Snippet(
            content=self.content,
            start=min(self.start, other.start),
            end=max(self.end, other.end),
            file_path=self.file_path,
        )

    @property
    def xml(self):
        return f"""<snippet source="{self.file_path}:{self.start}-{self.end}">\n{self.get_snippet()}\n</snippet>"""

    def get_url(self, repo_name: str, commit_id: str = "main"):
        num_lines = self.content.count("\n") + 1
        encoded_file_path = quote(self.file_path, safe="/")
        return f"https://github.com/{repo_name}/blob/{commit_id}/{encoded_file_path}#L{max(self.start, 1)}-L{min(self.end, num_lines)}"

    def get_markdown_link(self, repo_name: str, commit_id: str = "main"):
        num_lines = self.content.count("\n") + 1
        base = commit_id + "/" if commit_id != "main" else ""
        return f"[{base}{self.file_path}#L{max(self.start, 1)}-L{min(self.end, num_lines)}]({self.get_url(repo_name, commit_id)})"

    def get_slack_link(self, repo_name: str, commit_id: str = "main"):
        num_lines = self.content.count("\n") + 1
        base = commit_id + "/" if commit_id != "main" else ""
        return f"<{self.get_url(repo_name, commit_id)}|{base}{self.file_path}#L{max(self.start, 1)}-L{min(self.end, num_lines)}>"

    def get_preview(self, max_lines: int = 5):
        snippet = "\n".join(
            self.content.splitlines()[
                self.start : min(self.start + max_lines, self.end)
            ]
        )
        if self.start > 1:
            snippet = "\n" + snippet
        if self.end < self.content.count("\n") + 1 and self.end > max_lines:
            snippet = snippet + "\n"
        return snippet

    def expand(self, num_lines: int = 25):
        return Snippet(
            content=self.content,
            start=max(self.start - num_lines, 1),
            end=min(self.end + num_lines, self.content.count("\n") + 1),
            file_path=self.file_path,
        )

    @property
    def denotation(self):
        return f"{self.file_path}:{self.start}-{self.end}"


class DiffSummarization(RegexMatchableBaseModel):
    content: str
    _regex = r"""<file_summaries>(\n)?(?P<content>.*)$"""

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        result = super().from_string(string, **kwargs)
        result.content = result.content.replace("</file_summaries>", "", 1).strip()
        return cls(
            content=result.content,
        )


class PullRequestComment(RegexMatchableBaseModel):
    changes_required: str
    content: str
    _regex = r"""<changes_required>(?P<changes_required>.*)<\/changes_required>(\s+)<review_comment>(?P<content>.*)<\/review_comment>"""


class NoFilesException(Exception):
    def __init__(self, message="Sweep could not find any files to modify"):
        super().__init__(message)


class PRChangeRequest(BaseModel):
    params: dict


class MockPR(BaseModel):
    # Used to mock a PR object without creating a PR (branch will be created tho)
    file_count: int = 0  # Number of files changes
    title: str
    body: str
    pr_head: str
    base: Any
    head: Any
    assignee: Any = None

    id: int = -1
    state: str = "open"
    html_url: str = ""

    def create_review(self, *args, **kwargs):
        # Todo: used to prevent erroring in on_review.py file
        pass

    def create_issue_comment(self, *args, **kwargs):
        pass


@dataclass
class SandboxExecution:
    command: str
    output: str
    exit_code: int


class SandboxResponse(BaseModel):
    success: bool
    outputs: list[str]
    updated_content: str
    error_messages: list[str]


class MaxTokensExceeded(Exception):
    def __init__(self, filename):
        self.filename = filename


class UnneededEditError(Exception):
    def __init__(self, filename):
        self.filename = filename


class MatchingError(Exception):
    def __init__(self, filename):
        self.filename = filename


class EmptyRepository(Exception):
    def __init__(self):
        pass


@dataclass
class AssistantRaisedException(Exception):
    message: str
