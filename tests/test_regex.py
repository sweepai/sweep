

import os
import string
from typing import Literal, Self, Type

from loguru import logger
from sweepai.core.entities import FileChangeRequest, FilesToChange, RegexMatchableBaseModel


example = """<create>
</create>

<modify>
</modify>"""

file_change_requests = []

files_to_change = FilesToChange.from_string(example)
files_to_create: list[str] = files_to_change.files_to_create.split("\n*")
files_to_modify: list[str] = files_to_change.files_to_modify.split("\n*")
for file_change_request, change_type in zip(
    files_to_create + files_to_modify,
    ["create"] * len(files_to_create)
    + ["modify"] * len(files_to_modify),
):
    file_change_request = file_change_request.strip()
    if not file_change_request or file_change_request == "* None":
        continue
    logger.debug(file_change_request)
    logger.debug(change_type)
    file_change_requests.append(
        FileChangeRequest.from_string(
            file_change_request, change_type=change_type
        )
    )
print(file_change_requests)
fcr = FileChangeRequest.from_string(example)