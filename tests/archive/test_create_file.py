import re

from sweepai.core.entities import FileCreation

create_file_response = """create_file_resp"
"""
file_change = FileCreation.from_string(create_file_response)
print(file_change.code)
commit_message_match = re.search(
    'Commit message: "(?P<commit_message>.*)"', create_file_response
)
if commit_message_match:
    file_change.commit_message = commit_message_match.group("commit_message")
assert file_change is not None
file_change.commit_message = file_change.commit_message[
    : min(len(file_change.commit_message), 50)
]
