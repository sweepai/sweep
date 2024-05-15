from dataclasses import dataclass


@dataclass
class CodeReviewIssue:
    issue_description: str
    start_line: int
    end_line: int

@dataclass
class CodeReview:
    file_name: str
    diff_summary: str
    issues: list[CodeReviewIssue]

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
    annotations: list[str] = []