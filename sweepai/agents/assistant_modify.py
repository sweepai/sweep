import traceback

from loguru import logger

from sweepai.agents.assistant_wrapper import (
    client,
    openai_assistant_call,
    run_until_complete,
)
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.utils.chat_logger import ChatLogger, discord_log_error

long_file_helper_functions = r"""def print_lines(i, j):
    start = max(0, i - 10)
    end = min(len(original_lines), j + 10)

    for index in range(start, end):
        if index == i:
            print("\n--- Start of snippet ---")
        elif index == j:
            print("--- End of snippet ---\n")

        print(f"{{index}}: {{original_lines[index]}}")
    print("\n")

def print_lines_with_keywords(keywords):
    context = 10

    matches = [i for i, line in enumerate(original_lines) if any(keyword in line.lower() for keyword in keywords)]
    expanded_matches = set()

    for match in matches:
        start = max(0, match - context)
        end = min(len(original_lines), match + context + 1)
        for i in range(start, end):
            expanded_matches.add(i)

    for i in sorted(expanded_matches):
        print(f"{{i}}: {{original_lines[i]}}")
"""


short_file_helper_functions = r"""def print_lines(i, j):
    for index in range(0, len(original_lines)):
        if index == i:
            print("\n--- Start of snippet ---")
        elif index == j:
            print("--- End of snippet ---\n")

        print(f"{{index}}: {{original_lines[index]}}")
    print("\n")

# Print all lines initially
for i, line in enumerate(original_lines):
    print(f"{{i}}: {{line}}")
"""

system_message = r"""You're an engineer assigned to make an edit to solve a GitHub issue. Modify the attached file to complete the task by writing Python code to read and make edits to the file.

# Guide
## Step 1: Reading
First setup all the relevant modules and read the relevant lines by running:

### HELPER FUNCTIONS TO RUN
```python
import difflib
import ast

file_path = '/mnt/data/path/to/file'
with open(file_path, 'r') as file:
    file_content = file.read()
original_lines = file_content.splitlines()

{helper_functions}

def check_valid_python(code):
    try:
        # Check for valid python
        ast.parse(code)
        print("Python code is valid.")
    except SyntaxError as e:
        print("SyntaxError:", e)

def print_diff(new_content, old_content=file_content):
    print(difflib.unified_diff(
        file_content, current_content
    ))

def set_indentation(code, indent_size=4):
    lines = [line for line in code.split('\n') if line.strip()]
    min_indent = min(len(line) - len(line.lstrip()) for line in lines)
    return '\n'.join(' ' * indent_size + line[min_indent:] for line in lines)

current_content = file_content # this will be used later
```

Then, use the helper functions to determine the minimal set of lines of code to modify to solve the intended task.

## Step 2: Execution
You will iteratively make small edits. Before making each edit, make a backup of the current_content by running

```python
prev_content = current_content
```

### Modification script
For each section to change, run one of the following. Prefer modifying the least amount of lines of code that accomplishes the task to avoid mistakes:

```python
# Remember to escape quotations
old_content = "Old content"
new_content = "New content"
assert old_content in current_content
current_content = current_content.replace(old_content, new_content, 1) # avoid other accidental changes
```

### Validation
Then review the changes of the current edit by running

```python
# Double check the change
print_diff(current_content, prev_content)

# Check for valid python
check_valid_python(current_content)
```

### Revert (optional)
If the change is bad you can revert it by running

```python
current_content = prev_content
# then try making the change again
```

Then go back to Step 2 to make the edit. Move to Step 3 once all the edits are completed.

## Step 3: Output
Make a final review once at the end with:

```python
print(current_content)
check_valid_python(current_content)
print_diff(current_content)
```

Once you are done, give me the output and attach the file."""


def new_modify(
    request: str,
    file_path: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = "asst_LeUB6ROUIvzm97kjqATLGVgC",
    start_line: int = -1,
    end_line: int = -1,
):
    try:
        file_content = open(file_path, "r").read()
        if start_line > 0 and end_line > 0:
            request += (
                f"\n\nThe relevant lines are between {start_line} and {end_line}.\n\n"
            )
        response = openai_assistant_call(
            request=request,
            instructions=system_message.format(
                helper_functions=short_file_helper_functions
                if len(file_content.splitlines()) < 100
                else long_file_helper_functions,
            ),
            additional_messages=additional_messages,
            file_paths=[file_path],
            chat_logger=chat_logger,
            assistant_id=assistant_id,
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
                assistant_id=response.assistant_id,
            )
            try:
                file_object = messages.data[0].file_ids[0]
            except Exception:
                raise AssistantRaisedException(
                    f"Assistant never provided a file. Here is the last message: {messages.data[0].content[0].text.value}"
                )
        file_content = client.files.content(file_id=file_object).content.decode("utf-8")
        # delete the file afterwards
        client.files.delete(file_id=file_object)
    except AssistantRaisedException as e:
        discord_log_error(
            str(e)
            + "\n\n"
            + traceback.format_exc()
            + "\n\n"
            + str(chat_logger.data if chat_logger else "")
        )
        raise e
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


instructions = """Sweep: Move the payment_message and payment_message_start creation logic out of on_ticket.py into a separate function at the end of the file.
It should be the section of code relating to payment and deciding if it's a paying user 10 lines before the instantiation of payment_message.

You are a genius software engineer assigned to a GitHub issue. You will be given the repo as a zip file. Your job is to find the relevant files from the repository to construct a plan."""

if __name__ == "__main__":
    new_modify(
        instructions,
        "sweepai/handlers/on_ticket.py",
        chat_logger=ChatLogger({"username": "kevinlu1248"}),
    )
