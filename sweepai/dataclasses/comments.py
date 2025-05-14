from dataclasses import dataclass


@dataclass
class CommentDiffSpan:
    old_start_line: int
    old_end_line: int
    new_start_line: int
    new_end_line: int
    new_code: str
    file_name: str