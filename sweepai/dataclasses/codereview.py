from dataclasses import dataclass, field


@dataclass
class CodeReviewIssue:
    file_name: str
    issue_description: str
    line_number: str

    def __hash__(self):
        return hash((self.file_name, self.issue_description, self.line_number))
    
@dataclass
class PRReviewComment:
    thread_id: str
    file_name: str
    line_number: int
    body: str
    is_resolved: bool
    is_outdated: bool
    author: str

@dataclass
class PRReviewCommentThread:
    thread_id: str
    file_name: str
    line_number: int
    is_resolved: bool
    is_outdated: bool
    comments: list[PRReviewComment]


@dataclass
class CodeReview:
    file_name: str
    diff_summary: str
    issues: list[CodeReviewIssue]
    potential_issues: list[CodeReviewIssue]

@dataclass
class CodeReviewByGroup:
    file_names: list[str]
    diff_summary: str
    issues: list[CodeReviewIssue]
    potential_issues: list[CodeReviewIssue]

    @property
    def group_name(self):
        return ",".join(self.file_names)

    def get_all_file_names(self):
        return ", ".join(self.file_names)

@dataclass
class Patch:
    file_name: str
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

@dataclass
class GroupedFilesForReview:
    file_names: list[str]
    rendered_changes: str # full rendered changes
    rendered_patches: str # only has rendered patches
    rendered_source_code: str # only has rendered patches

    @property
    def group_name(self):
        return ",".join(self.file_names)
    
    def get_group_name(self):
        return ",".join(self.file_names)
    
    def get_all_file_names(self):
        return ", ".join(self.file_names)

    def is_file_in_group(self, file_name):
        return file_name in self.file_names
