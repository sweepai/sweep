import traceback

from loguru import logger

from sweepai.agents.assistant_wrapper import (
    client,
    openai_assistant_call,
    run_until_complete,
)
from sweepai.core.entities import Message
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.regex_utils import search_xml

search_system_message = r"""# User Request
{user_request}

# Instructions
Find the relevant lines in the attached file to complete the task by executing Python code to read sections of the file.

# Guide
## Step 1: Reading and Setup
First, read the file and set up helper functions by running:

### SETUP CODE TO RUN
```python
file_path = '/mnt/data/path/to/file'
with open(file_path, 'r') as file:
    file_content = file.read()
original_lines = file_content.splitlines()

def print_lines(i, j):
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


len(original_lines)
```

## Step 1: Iterative Search
Then search for keywords or use regex search based on the user request to find relevant lines via

### Keyword Search
```python
keywords = ["foo", "bar"]
print_lines_with_keywords(keywords)
```

### Viewing Spans
Then for each potentially relevant section, print the surrounding lines and determine if they are actually relevant.

```python
print_lines(a - 20, b + 20)
print_lines(c - 20, d + 20)
```

Ensure that the code between "--- Start of snippet ---" and "--- End of snippet ---" is valid code and doesn't break the syntax.

If necessary, re-run either steps with bigger spans on lines or other keywords.

## Step 3: Review Final Answer
Finally, identify and list the minimal precise lines of code that should be modified to complete the task. Prefer multiple small edits over one large edit.

### Validate Answer
Before submitting the final answer, double-check the surrounding lines. If a:b seems relevant, check for the surrounding potentially relevant sections, and check that lines a:b represent coherent unfragmented code

```python
print_lines(a, b)
```

### Answer Format
If still it looks like lines a:b represent precise and relevant line numbers, give me the output in the following format:

```xml
<relevant_lines>
- lines a:b+1 - change foo to bar
- line c:d+1 - add baz
...
</relevant_lines>
```

Make sure you add 1 since the line numbers include the start and exclude the end. You may not necessarily need multiple spans."""

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
"""

system_message = r"""# User Request
{user_request}

# Instructions
Modify the attached file to complete the task by writing Python code to read and make edits to the file.

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


def code_file_search(
    request: str, file_path: str, chat_logger: ChatLogger | None = None
):
    try:
        response = openai_assistant_call(
            name="Python Code Search Modification Assistant",
            instructions=search_system_message.format(user_request=request),
            file_paths=[file_path],
            chat_logger=chat_logger,
        )
        messages = response.messages
        final_response = messages.data[0].content[0].text.value
        relevant_lines = search_xml(final_response, "relevant_lines")
    except Exception as e:
        logger.exception(e)
        discord_log_error(str(e) + "\n\n" + traceback.format_exc())
        return None
    return relevant_lines


def new_modify(
    request: str,
    file_path: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
):
    try:
        # relevant_lines = code_file_search(request, file_path, chat_logger)
        file_content = open(file_path, "r").read()
        response = openai_assistant_call(
            name="Python Code Modification Assistant",
            instructions=system_message.format(
                user_request=request,
                helper_functions=short_file_helper_functions
                if len(file_content.splitlines()) < 100
                else long_file_helper_functions,
            ),
            additional_messages=additional_messages,
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
    # code_file_search("Add type hints to this file.", "sweepai/agents/complete_code.py")
    code_file_search(
        "Move the payment-related messaging section (it's a 20-line section of code) out of on_ticket.py into a separate function at the end of the file",
        "sweepai/handlers/on_ticket.py",
    )
