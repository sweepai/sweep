import os
import re
import string
from typing import ClassVar, Literal, Type, TypeVar, Any
from github.Branch import Branch
from loguru import logger
from pydantic import BaseModel

Self = TypeVar("Self", bound="RegexMatchableBaseModel")


class Message(BaseModel):
    role: Literal["system"] | Literal["user"] | Literal["assistant"] | Literal["function"]
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
            **{k: (v if v else "").strip() for k, v in match.groupdict().items()},
            **kwargs,
        )


class FilesToChange(RegexMatchableBaseModel):
    files_to_modify: str
    files_to_create: str

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        create_pattern = r"""<create_file>(?P<files_to_create>.*)</create_file>"""
        create_match = re.search(create_pattern, string, re.DOTALL)
        modify_pattern = r"""<modify_file>(?P<files_to_modify>.*)</modify_file>"""
        modify_match = re.search(modify_pattern, string, re.DOTALL)
        return cls(
            files_to_create=create_match.groupdict()["files_to_create"].strip() if create_match else "* None",
            files_to_modify=modify_match.groupdict()["files_to_modify"].strip() if modify_match else "* None",
        )
    
class RewrittenTitleAndDescription(RegexMatchableBaseModel):
    new_title: str
    new_description: str

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        title_pattern = r"""<issue_title>(?P<new_title>.*)</issue_title>"""
        title_match = re.search(title_pattern, string, re.DOTALL)
        description_pattern = r"""<issue_description>(?P<new_description>.*)</issue_description>"""
        description_match = re.search(description_pattern, string, re.DOTALL)
        return cls(
            new_title=title_match.groupdict()["new_title"].strip() if title_match else None,
            new_description=description_match.groupdict()["new_description"].strip() if description_match else None,
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
            additional_instructions=instructions_match.groupdict()["additional_instructions"].strip() if instructions_match else "",
        )

# todo (fix double colon regex): Update the split from "file_tree.py : desc" to "file_tree.py\tdesc"
# tab supremacy
def clean_filename(file_name: str):
    valid_chars = "-_./$[]%s%s" % (string.ascii_letters, string.digits)
    file_name = ''.join(c for c in file_name if c in valid_chars)
    file_name = file_name.replace(' ', '')
    file_name = file_name.strip('`')
    return os.path.normpath(file_name)


def clean_instructions(instructions: str):
    return instructions.strip()


class FileChangeRequest(RegexMatchableBaseModel):
    filename: str
    instructions: str
    change_type: Literal["modify"] | Literal["create"]

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        colon_idx = string.find(':')
        file_name = string[:colon_idx]
        instructions = string[colon_idx + 1:]
        file_name = clean_filename(file_name)
        instructions = clean_instructions(instructions)
        file_name = file_name.lstrip('/')
        res = FileChangeRequest(filename=file_name,
                                instructions=instructions,
                                change_type="modify")
        return res


class FileCreation(RegexMatchableBaseModel):
    commit_message: str
    code: str
    _regex = r'''commit_message\s?=\s?"?(?P<commit_message>.*?)"?\n(?P<code>.*)'''
    # Regex updated to support ``` outside of <new_file> tags

    # _regex = r"""Commit Message:(?P<commit_message>.*)<new_file>(python|javascript|typescript|csharp|tsx|jsx)?(?P<code>.*)$"""
    # _regex = r"""Commit Message:(?P<commit_message>.*)(<new_file>|```)(python|javascript|typescript|csharp|tsx|jsx)?(?P<code>.*)($|```)"""

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        result = super().from_string(string, **kwargs)

        first_index = result.code.find("<new_file>")
        if first_index >= 0:
            last_index = result.code.rfind("</new_file>")
            result.code = result.code[first_index + len('<new_file>'):last_index]
        else:
            first_index = result.code.find("```")
            if first_index >= 0:
                last_index = result.code.rfind("```")
                result.code = result.code[first_index:last_index]
            else:
                raise ValueError("No <new_file> tags or ``` found in code block")

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
            last_newline = result.code.rfind("\n")
            result.code = result.code[first_newline + 1:]
            result.code = result.code[: last_newline]
        result.code += "\n"
        return result


class PullRequest(RegexMatchableBaseModel):
    title: str
    branch_name: str
    content: str
    _regex = r'''pr_title\s+=\s+"(?P<title>.*?)"\n+branch\s+=\s+"(?P<branch_name>.*?)"\n+pr_content\s+=\s+"""(?P<content>.*?)"""'''


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
            return self.file_path == other.file_path and self.start == other.start and self.end == other.end
        return False

    def __hash__(self):
        return hash((self.file_path, self.start, self.end))

    def get_snippet(self):
        snippet = "\n".join(self.content.splitlines()[self.start:self.end])
        if self.start > 1:
            snippet = '...\n' + snippet
        if self.end < self.content.count('\n') + 1:
            snippet = snippet + '\n...'
        return snippet

    def __add__(self, other):
        assert self.content == other.content
        assert self.file_path == other.file_path
        return Snippet(
            content=self.content,
            start=self.start,
            end=other.end,
            file_path=self.file_path
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
            file_path=self.file_path
        )

    @property
    def xml(self):
        return f"""<snippet source="{self.file_path}:{self.start}-{self.end}">\n{self.get_snippet()}\n</snippet>"""

    def get_url(self, repo_name: str, commit_id: str = "main"):
        num_lines = self.content.count("\n") + 1
        return f"https://github.com/{repo_name}/blob/{commit_id}/{self.file_path}#L{max(self.start, 1)}-L{min(self.end, num_lines)}"

    def get_markdown_link(self, repo_name: str, commit_id: str = "main"):
        num_lines = self.content.count("\n") + 1
        base = commit_id + "/" if commit_id != "main" else ""
        return f"[{base}{self.file_path}#L{max(self.start, 1)}-L{min(self.end, num_lines)}]({self.get_url(repo_name, commit_id)})"

    def get_slack_link(self, repo_name: str, commit_id: str = "main"):
        num_lines = self.content.count("\n") + 1
        base = commit_id + "/" if commit_id != "main" else ""
        return f"<{self.get_url(repo_name, commit_id)}|{base}{self.file_path}#L{max(self.start, 1)}-L{min(self.end, num_lines)}>"

    def get_preview(self, max_lines: int = 5):
        snippet = "\n".join(self.content.splitlines()[self.start:min(self.start + max_lines, self.end)])
        if self.start > 1:
            snippet = '\n' + snippet
        if self.end < self.content.count('\n') + 1 and self.end > max_lines:
            snippet = snippet + '\n'
        return snippet

    def expand(self, num_lines: int = 35):
        return Snippet(
            content=self.content,
            start=max(self.start - num_lines, 1),
            end=min(self.end + num_lines, self.content.count("\n") + 1),
            file_path=self.file_path
        )

    @property
    def denotation(self):
        return f"{self.file_path}:{self.start}-{self.end}"


class DiffSummarization(RegexMatchableBaseModel):
    content: str
    _regex = r"""<file_summarization>(?P<content>.*)$"""

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        result = super().from_string(string, **kwargs)
        result.content = result.content.replace("</file_summarization>", "", 1).strip()
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
    type: str # "comment", or "gha"
    params: dict

class MockPR(BaseModel):
    # Used to mock a PR object without creating a PR (branch will be created tho)
    file_count: int = 0  # Number of files changes
    title: str
    body: str
    pr_head: str
    base: Any
    head: Any

    state: str = "open"
    html_url: str = ""

    def create_review(self, *args, **kwargs):
        # Todo: used to prevent erroring in on_review.py file
        pass