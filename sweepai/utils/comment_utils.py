import os
import re


def check_comments_presence(file_path: str, new_code: str) -> bool:
    _, file_extension = os.path.splitext(file_path)
    comment_patterns = {
        ".py": "#",
        ".js": "//",
        ".ts": "//",
        ".jsx": "//",
        ".tsx": "//",
        ".java": "//",
        ".c": "/*",
        ".cpp": "//",
        ".cs": "//",
        ".php": "//",
        ".swift": "//",
        ".rb": "#",
    }
    if file_extension not in comment_patterns:
        return False
    comment_pattern = comment_patterns.get(file_extension, "")
    return bool(re.search(comment_pattern, new_code))
