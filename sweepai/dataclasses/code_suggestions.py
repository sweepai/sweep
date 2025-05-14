from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class CodeSuggestion:
    file_path: str
    original_code: str
    new_code: str
    file_contents: str = ""

@dataclass
class StatefulCodeSuggestion(CodeSuggestion):
    state: Literal["pending", "processing", "done", "error"] = "pending"
    error: Optional[str] = None

