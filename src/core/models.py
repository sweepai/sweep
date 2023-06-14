(python|javascript|typescript|csharp|tsx|jsx)?(?P<code>.*)$"""

    @classmethod
    def from_string(cls: Type[Self], string: str, **kwargs) -> Self:
        result = super().from_string(string, **kwargs)
        result.code = result.code.strip()
        if result.code.endswith("</new_file>"):
            result.code = result.code[: -len("</new_file>")]
        if result.code.startswith("```"):
            first_newline = result.code.find("\n")
            last_newline = result.code.rfind("\n")
            result.code = result.code[first_newline + 1 :]
            result.code = result.code[: last_newline]
        result.code += "\n"
        return result


class PullRequest(RegexMatchableBaseModel):
    title: str
    branch_name: str
    content: str
    _regex = r"""Title:(?P<title>.*)Branch Name:(?P<branch_name>.*)<content>(python|javascript|typescript|csharp|tsx|jsx)?(?P<content>.*)</content>"""


class Snippet(BaseModel):
    """
    Start and end refer to line numbers
    """
    
    content: str
    start: int
    end: int
    file_path: str
    is_snippet_file_start: bool = False
    is_snippet_file_end: bool = False

    def get_snippet(self):
        return "\n".join(self.content.splitlines()[self.start:self.end])

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
        return f"""<snippet filepath="{self.file_path}" start="{self.start}" end="{self.end}">\n{self.get_snippet()}\n</snippet>"""
    
class DiffSummarization(RegexMatchableBaseModel):
    content: str
    _regex = r"""<file_summarization>(?P<content>.*)<\/file_summarization>"""

class PullRequestComment(RegexMatchableBaseModel):
    content: str
    _regex = r"""<review_comment>(?P<content>.*)<\/review_comment>"""
