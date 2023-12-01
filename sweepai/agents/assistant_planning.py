import copy
import re
import traceback
import uuid

from loguru import logger

from sweepai.agents.assistant_wrapper import openai_assistant_call
from sweepai.core.entities import AssistantRaisedException, FileChangeRequest, Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error

system_message = r"""# User Request
{user_request}

# Guide
## Step 1: Unzip the file into /mnt/data/repo and list all root level directories.

## Step 2: Find the relevant files.
You can search by file name or by keyword search in the contents.

## Step 3: Find relevant lines.
1. Locate the lines of code that contain the identified keywords or are at the specified line number. You can use keyword search or manually look through the file 100 lines at a time.
2. Check the surrounding lines to establish the full context of the code block. 
3. Adjust the starting line to include the entire functionality that needs to be refactored or moved.
4. Finally determine the exact line spans that include a logical and complete section of code to be edited.

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
        print(f"{{i}}: {{content.splitlines()[i]}}")
```

## Step 4: Construct a plan
Provide the final plan to solve the issue, following these rules:
* You may only create new files and modify existing files.
* File paths should be relative paths from the root of the repo.
* Do not generate more than one modification or creation per file unless absolutely necessary.
* Start and end lines indicate the exact start and end lines to edit. Expand this to encompass more lines if you're unsure where to make the exact edit.

Respond in the following format:

```xml
<plan>
<create_file file="file_path_1">
* Natural language instructions for creating the new file needed to solve the issue.
* Reference necessary files, imports and entity names.
...
</create_file>
...

<modify_file file="file_path_2" start_line="i" end_line="j">
* Natural language instructions for the modifications needed to solve the issue. 
* Be concise and reference necessary files, imports and entity names.
...
</modify_file>
...

</plan>
```"""

@file_cache(ignore_params=["zip_path", "chat_logger"])
def new_planning(
    request: str,
    zip_path: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = "asst_iFwIYazVKJx1fn4g28vkVZ70",
) -> list[FileChangeRequest]:
    try:
        response = openai_assistant_call(
            request=request,
            assistant_id=assistant_id,
            additional_messages=additional_messages,
            file_paths=[zip_path],
            chat_logger=chat_logger,
            instructions=system_message.format(user_request=request),
        )
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
            fcr.filename = fcr.filename.lstrip("/")
            fcr.instructions = fcr.instructions.replace("\n*", "\n•")
            fcr.instructions = fcr.instructions.strip("\n")
            if fcr.instructions.startswith("*"):
                fcr.instructions = "•" + fcr.instructions[1:]
            fcrs.append(fcr)
            new_file_change_request = copy.deepcopy(fcr)
            new_file_change_request.change_type = "check"
            new_file_change_request.parent = fcr
            new_file_change_request.id_ = str(uuid.uuid4())
            fcrs.append(new_file_change_request)
        assert len(fcrs) > 0
        return fcrs
    except AssistantRaisedException as e:
        raise e
    except Exception as e:
        logger.exception(e)
        if chat_logger is not None:
            discord_log_error(
                str(e)
                + "\n\n"
                + traceback.format_exc()
                + "\n\n"
                + str(chat_logger.data)
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
