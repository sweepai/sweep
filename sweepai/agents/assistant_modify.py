from sweepai.agents.assistant_wrapper import client, openai_assistant_call

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
Then, identify and list all sections of code that should be modified. Be specific, reference line numbers, and prefer multiple small edits over one large edit. Indicate the minimal amount of lines that need to be modified to complete the task.

## Step 3: Execution

First make a backup of the current_lines by running

```python
prev_lines = current_lines
```

### Modification script
For each section to change, run one of the following. Prefer modifying the least amount of lines to avoid mistakes:

#### Single-line replace
```python
new_content = "New content goes here".strip("\n")
current_lines[i] = new_content
```

#### Multi-line replace
```python
new_content = \"\"\"
New content goes here
\"\"\".strip("\n")
current_lines[i:j] = new_content
```

### Validation
Then review the changes by running

```python
# Double check the change
import difflib
diff = difflib.unified_diff(
    prev_lines.splitlines(keepends=True), current_lines.splitlines(keepends=True)
)

# Check for valid python
import ast
ast.parse("\n".join(lines))
```

### Revert (optional)
If the change is bad you can revert it by running

```python
current_lines = prev_lines
# then try making the change again
```

## Step 4: Output
```python
for line in current_lines:
    print(line)
```

Then give me the output and attach the file.
"""


def new_modify(
    request="Add type hints to this file.",
    file_path="sweepai/agents/complete_code.py",
):
    messages = openai_assistant_call(
        name="Python Modification Assistant",
        instructions=system_message.format(user_request=request),
        file_paths=[file_path],
    )
    file_object = messages.data[0].file_ids[0]
    file_content = client.files.content(file_id=file_object).content.decode("utf-8")
    return file_content


if __name__ == "__main__":
    new_modify()
