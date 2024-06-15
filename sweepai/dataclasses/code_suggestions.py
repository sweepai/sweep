from dataclasses import dataclass


@dataclass
class CodeSuggestion:
    file_path: str
    original_code: str
    new_code: str

    original_entire_code: str = ""
