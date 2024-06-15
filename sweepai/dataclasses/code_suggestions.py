from dataclasses import dataclass


@dataclass
class CodeSuggestion:
    file_path: str
    original_code: str
    new_code: str
