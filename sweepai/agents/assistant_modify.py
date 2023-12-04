import os
import re
import traceback
import uuid
from pathlib import Path

from loguru import logger

from sweepai.agents.assistant_wrapper import (
    client,
    openai_assistant_call,
    run_until_complete,
)
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.core.helpers import helper_methods_contents
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.patch_utils import apply_patch
from sweepai.utils.progress import AssistantConversation, TicketProgress

short_file_helper_functions = r"""def print_original_lines(i, j):
    for index in range(0, len(original_lines)):
        if index == i:
            print("\n--- Start of snippet ---")
        elif index == j:
            print("--- End of snippet ---\n")

        print(f"{{index}}: {{original_lines[index]}}")
    print("\n")

# Print all lines initially
for i, line in enumerate(original_lines):
    print(f"{{i}}: {{line}}")"""

instructions_message = """\
You're a brilliant engineer assigned to make an edit to solve a GitHub issue. Modify the attached file to complete the task by writing Python code to read and make edits to the file. Be careful of syntax errors, such as multiline variables, indentation, and string formatting. You must complete all three steps before returning your response.

# Guide
## Step 1: Setup Helper Functions and Identify Relevant Lines
First instantiate and run all of the following code. Then identify the relevant lines by running `print_original_lines` and `print_original_lines_with_keywords`:

### HELPER FUNCTIONS TO RUN
```python
# First read and load the helper functions into the current context. This will allow you to use the helper functions in the rest of the code.
helper_methods_path = '/mnt/data/{file_id}'
with open(helper_methods_path, 'r') as f:
    helper_methods = f.read()
print(helper_methods)
exec(helper_methods)
```

Use the helper functions to identify the minimum set of lines of code you must modify.

## Step 2: Iterative Code Modification
You will iteratively make small edits. Before making each edit, make a backup of the current_content by running:

```python
prev_content = current_content
```

### Modification script
For each section to change, run one of the following:

```python
# Remember to escape quotations
old_content = "Old content"
new_content = "New content"
assert old_content in current_content # if this fails then identify a new section to change
current_content = current_content.replace(old_content, new_content, 1) # avoid other accidental changes
```

### Validation
Then review the changes of the current edit by running:

```python
# Double check the change
print_diff(current_content, prev_content)

# Check for valid python
check_valid_python(current_content)
```

### Revert (optional)
If the change is invalid or looks incorrect, revert it by running the below snippet and trying again:

```python
current_content = prev_content
# then try making the change again, optionally using set_indentation(code, num_indents=4) to fix indentation
```

Move to Step 3 once all the edits are completed.

## Step 3: Final Review and Response
Perform a final review once all edits from Step 2 are completed. Use the following code:

```python
print(current_content)
check_valid_python(current_content)
print_diff(current_content, final_diff=True)
```

Finally, print the final valid diff using the print_diff function."""

allowed_exts = [
    "c",
    "cpp",
    "csv",
    "docx",
    "html",
    "java",
    "json",
    "md",
    "pdf",
    "php",
    "pptx",
    "py",
    "rb",
    "tex",
    "txt",
    "css",
    "jpeg",
    "jpg",
    "js",
    "gif",
    "png",
    "tar",
    "ts",
    "xlsx",
    "xml",
    "zip",
]


@file_cache(ignore_params=["file_path", "chat_logger"])
def new_modify(
    request: str,
    file_path: str,
    file_contents: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = "asst_SgttsEvgZWJBc0mbnHkJe1pE",
    start_line: int = -1,
    end_line: int = -1,
    ticket_progress: TicketProgress | None = None,
    assistant_conversation: AssistantConversation | None = None,
):
    modify_iterations = 5
    try:
        def save_ticket_progress(assistant_id: str, thread_id: str, run_id: str):
            assistant_conversation.update_from_ids(
                assistant_id=assistant_id, run_id=run_id, thread_id=thread_id
            )
            ticket_progress.save()

        file_content = open(file_path, "r").read()
        if start_line > 0 and end_line > 0:
            request += (
                f"\n\nThe relevant lines are between {start_line} and {end_line}.\n\n"
            )
        request = f"This is the file:\n{file_content}\n" + f"# Instructions:\n{request}"
        if not any(file_path.endswith(ext) for ext in allowed_exts):
            os.rename(file_path, file_path + ".txt")
            file_path += ".txt"
        target_file_object = client.files.create(
            file=Path(file_path), purpose="assistants"
        )
        target_file_id = target_file_object.id
        formatted_helper_method_contents = helper_methods_contents.format(
            target_file_id=f"/mnt/data/{target_file_id}"
        )
        tmp_helper_file_path = f"/tmp/helper_{uuid.uuid4()}.py"
        with open(tmp_helper_file_path, "w") as f:
            f.write(formatted_helper_method_contents)
        helper_methods_file_id = client.files.create(
            file=Path(tmp_helper_file_path), purpose="assistants"
        ).id
        os.remove(tmp_helper_file_path)
        uploaded_file_ids = [target_file_id, helper_methods_file_id]
        response = openai_assistant_call(
            request=request,
            instructions=instructions_message.format(file_id=helper_methods_file_id),
            additional_messages=additional_messages,
            uploaded_file_ids=uploaded_file_ids,
            chat_logger=chat_logger,
            assistant_id=assistant_id,
            save_ticket_progress=save_ticket_progress
            if ticket_progress is not None
            else None,
            assistant_name="Code Modification Assistant",
        )
        save_ticket_progress()
        messages = response.messages
        final_diff = None
        final_diff_pattern = r"<final_diff>\n(.*?)</final_diff>"
        run_id = response.run_id
        thread_id = response.thread_id
        for _ in range(modify_iterations):
            try:
                # try to get the patch
                steps = client.beta.threads.runs.steps.list(
                    run_id=run_id, thread_id=thread_id
                )
                all_code_interpreter_outputs = []
                for step in steps.data:
                    if step.type == "tool_calls":
                        code_interpreter = step.step_details.tool_calls[
                            0
                        ].code_interpreter
                        if (
                            code_interpreter
                            and code_interpreter.outputs
                            and code_interpreter.outputs[0].logs
                        ):
                            all_code_interpreter_outputs.append(
                                code_interpreter.outputs[0].logs
                            )
                for output in all_code_interpreter_outputs:
                    if final_diff_match := re.search(
                        final_diff_pattern, output, re.DOTALL
                    ):
                        final_diff = final_diff_match.group(1)
                        return apply_patch(file_contents, final_diff)
                else:
                    logger.warning(
                        f"Assistant never provided a final_diff. Here is the last message: {messages.data[0].content[0].text.value}"
                    )
                    client.beta.threads.messages.create(
                        thread_id=thread_id,
                        role="user",
                        content="A valid final_diff was not provided. Please continue working on the code. If you are stuck, consider starting over.",
                    )
                    run = client.beta.threads.runs.create(
                        thread_id=response.thread_id,
                        assistant_id=response.assistant_id,
                        instructions=instructions_message.format(
                            file_id=helper_methods_file_id
                        ),
                    )
                    run_id = run.id
                    messages = run_until_complete(
                        thread_id=thread_id,
                        run_id=run_id,
                        assistant_id=response.assistant_id,
                    )
            except Exception:
                raise AssistantRaisedException(
                    f"Assistant never provided a final_diff. Here is the last message: {messages.data[0].content[0].text.value}"
                )
        try:
            client.files.delete(target_file_id)
            client.files.delete(helper_methods_file_id)
        except Exception as e:
            logger.warning(e)
    except AssistantRaisedException as e:
        discord_log_error(
            str(e)
            + "\n\n"
            + traceback.format_exc()
            + "\n\n"
            + str(chat_logger.data if chat_logger else "")
        )
    except Exception as e:
        logger.exception(e)
        # TODO: Discord
        discord_log_error(
            str(e)
            + "\n\n"
            + traceback.format_exc()
            + "\n\n"
            + str(chat_logger.data if chat_logger else "")
        )
        return None
    return file_content


if __name__ == "__main__":
    instructions = """• Replace the broken installation link with the provided new link.\n• Change the text from "check out our [tutorial on running Sweep on Docusaurus](https://docs.sweep.dev/tutorial)." \n  to "check out our [tutorial on running Sweep on Docusaurus](https://docs.sweep.dev/usage/tutorial).\""""
    additional_messages = [Message(role='user', content='# Repo & Issue Metadata\nRepo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.\nIssue Title: replace the broken installation link in installation.md with https://docs.sweep.dev/usage/tutorial', name=None, function_call=None, key='issue_metadata')]
    file_contents = open("docs/installation.md", "r").read()
    response = new_modify(
        instructions,
        "docs/installation.md",
        file_contents=file_contents,
        chat_logger=ChatLogger({"username": "wwzeng1"}),
        additional_messages=additional_messages,
    )
    import pdb

    pdb.set_trace()
