import traceback

from loguru import logger

from sweepai.agents.assistant_wrapper import (
    client,
    openai_assistant_call,
    run_until_complete,
)
from sweepai.utils.chat_logger import ChatLogger, discord_log_error

system_message = r"""{user_request}

# Instructions
Modify the attached file to complete the task by writing Python code to make edits to the file.

# Guide
## Step 1: Reading
First read the file with line numbers by running:

```python
file_path = '/mnt/data/path/to/file'
with open(file_path, 'r') as file:
    file_content = file.read()
original_lines = file_content.splitlines()
for i, line in enumerate(original_lines): # 0-index is better
    print(f"{{i}}: {{line}}")
current_lines = lines # this will be used later
```

## Step 2: Planning
Then, identify and list all sections of code that should be modified. Be specific, reference line numbers, and prefer multiple small edits over one large edit. Indicate the minimal set of lines that need to be modified to complete the task.

## Step 3: Execution

First make a backup of the current_content by running

```python
prev_content = current_content
```

### Modification script
For each section to change, run one of the following. Prefer modifying the least amount of lines of code to avoid mistakes:

```python
# Remember to escape quotations
old_content = "Old content"
new_content = "New content"
assert old_content in current_content
current_content = current_content.replace(old_content, new_content, count=1) # avoid other accidental changes
```

### Validation
Then review the changes by running

```python
# Double check the change
import difflib
diff = difflib.unified_diff(
    prev_content, current_content
)

# Check for valid python
import ast
ast.parse(current_content)
```

### Revert (optional)
If the change is bad you can revert it by running

```python
current_content = prev_content
# then try making the change again
```

## Step 4: Output
```python
print(current_content)
```

Then give me the output and attach the file."""


def new_modify(request: str, file_path: str, chat_logger: ChatLogger | None = None):
    try:
        response = openai_assistant_call(
            name="Python Modification Assistant",
            instructions=system_message.format(user_request=request),
            file_paths=[file_path],
            chat_logger=chat_logger,
        )
        messages = response.messages
        try:
            file_object = messages.data[0].file_ids[0]
        except Exception as e:
            logger.warning(e)
            run = client.beta.threads.runs.create(
                thread_id=response.thread_id,
                assistant_id=response.assistant_id,
                instructions="Please give me the final file.",
            )
            messages = run_until_complete(
                thread_id=response.thread_id,
                run_id=run.id,
            )
            file_object = messages.data[0].file_ids[0]
        file_content = client.files.content(file_id=file_object).content.decode("utf-8")
    except Exception as e:
        logger.exception(e)
        # TODO: Discord
        discord_log_error(str(e) + "\n\n" + traceback.format_exc())
        return None
    return file_content


if __name__ == "__main__":
    new_modify("Add type hints to this file.", "sweepai/agents/complete_code.py")
