import copy
import hashlib
import os
import re
import shutil
import time
import traceback
import uuid

from loguru import logger

from sweepai.agents.assistant_wrapper import openai_assistant_call
from sweepai.core.entities import FileChangeRequest, Message
from sweepai.utils.chat_logger import ChatLogger, discord_log_error

system_message = r"""# User Request
{user_request}

# Guide
## Step 1: Unzip the file into /mnt/data/repo and list all root level directory

## Step 2: Find the relevant files.
You can search by file name or by keyword search in the contents.

## Step 3: Find relevant lines.
1. Locate the lines of code that contain the identified keywords or are at the specified line number. You can use keyword search or manually look through the file 100 lines at a time.
2. Check the surrounding lines to establish the full context of the code block. If the initial lines identified do not seem to include the entire logical code block related to the task, adjust the starting line to include the necessary context for the entire functionality that needs to be refactored or moved.
4. Finally determine the exact line spans that includes a logical and complete section of code that should be edited.

```python
def print_lines_with_keyword(content, keywords):
    max_matches=5
    context = 10

    matches = [i for i, line in enumerate(content.splitlines()) if any(keyword in line.lower() for keyword in keywords)]
    print(f"Found {{len(matches}} matches, but capping at {{max_match}}")
    matches = matches[:max_matches]
    expanded_matches = set()

    for match in matches:
        start = max(0, match - context)
        end = min(len(content.splitlines()), match + context + 1)
        for i in range(start, end):
            expanded_matches.add(i)

    for i in sorted(expanded_matches):
        print(f"{{i}}: {{original_lines[i]}}")
```

## Step 4: Construct a plan
Provide the final plan to solve the issue, following these rules:
* You may only create new files and modify existing files
* File paths should be relative paths from the root of the repo
* Start and end lines indicate the exact start and end lines to edit. Expand this to encompass more lines if you're unsure where to make the exact edit.

Respond in the following format:

```xml
<plan>
<create_file file="file_path_1" read_only_relevant_snippets="optional list of space-separated relevant read-only file paths.">
* Natural language instructions for creating the new file needed to solve the issue
* Include references to all files, imports and entity names
...
</create_file>
...

<modify_file file="file_path_2" start_line="i" end_line="j" read_only_relevant_snippets="optional list of space-separated relevant read-only file paths">
* Natural language instructions for the modifications needed to solve the issue. Be concise and mention references to all files, imports and entity names.
...
</modify_file>
...

</plan>
```"""


def new_planning(
    request: str,
    repository_path: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = "asst_E644o8UsuqdA8iDXmP6bLROl",
) -> list[FileChangeRequest]:
    try:
        logger.info("Zipping repository...")
        archive_name = hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]
        shutil.make_archive(f"/tmp/{archive_name}", "zip", repository_path)
        logger.info(
            f"Done zipping repository. Calling OpenAI Assistant {assistant_id}..."
        )
        response = openai_assistant_call(
            request=request,
            assistant_id=assistant_id,
            additional_messages=additional_messages,
            file_paths=[f"/tmp/{archive_name}.zip"],
            chat_logger=chat_logger,
        )
        os.remove(f"/tmp/{archive_name}.zip")
        messages = response.messages
        final_message = messages.data[0].content[0].text.value
        fcrs = []
        for match_ in re.finditer(FileChangeRequest._regex, final_message, re.DOTALL):
            group_dict = match_.groupdict()
            if group_dict["change_type"] == "create_file":
                group_dict["change_type"] = "create"
            if group_dict["change_type"] == "modify_file":
                group_dict["change_type"] = "modify"
            fcr = FileChangeRequest(**group_dict)
            fcrs.append(fcr)
            new_file_change_request = copy.deepcopy(fcr)
            new_file_change_request.change_type = "check"
            new_file_change_request.parent = fcr
            new_file_change_request.id_ = str(uuid.uuid4())
            fcrs.append(new_file_change_request)
        assert len(fcrs) > 0
        return fcrs
    except Exception as e:
        logger.exception(e)
        # TODO: Discord
        discord_log_error(
            str(e) + "\n\n" + traceback.format_exc() + "\n\n" + str(chat_logger.data)
        )
        return None


instructions = """Sweep: Move the payment_message and payment_message_start creation logic out of on_ticket.py into a separate function at the end of the file.
It should be the section of code relating to payment and deciding if it's a paying user 10 lines before the instantiation of payment_message.

You are a genius software engineer assigned to a GitHub issue. You will be given the repo as a zip file. Your job is to find the relevant files from the repository to construct a plan."""

if __name__ == "__main__":
    print(
        new_planning(
            instructions,
            "/tmp/sweep",
            chat_logger=ChatLogger(
                {"username": "kevinlu1248", "title": "Unit test for planning"}
            ),
        )
    )
