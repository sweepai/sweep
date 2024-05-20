from dataclasses import dataclass, field


@dataclass
class CodeReviewIssue:
    issue_description: str
    start_line: int
    end_line: int

    def __hash__(self):
        return hash((self.issue_description, self.start_line, self.end_line))

@dataclass
class CodeReview:
    file_name: str
    diff_summary: str
    issues: list[CodeReviewIssue]
    potential_issues: list[CodeReviewIssue]

@dataclass
class Patch:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    changes: str

@dataclass
class PRChange:
    file_name: str
    diff: str
    old_code: str
    new_code: str
    status: str
    patches: list[Patch]
    annotations: list[str] = field(default_factory=list)

@dataclass
class FunctionDef:
    file_name: str
    function_code: str
    start_line: int
    end_line: int