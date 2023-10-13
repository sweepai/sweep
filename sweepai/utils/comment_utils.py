import re
import os

def check_comments_presence(file_path: str, new_code: str) -> bool:
    _, file_extension = os.path.splitext(file_path)
    comment_pattern = {
        '.py': '#',
        '.js': '//',
        '.ts': '//'
    }.get(file_extension, '')
    return bool(re.search(comment_pattern, new_code))
