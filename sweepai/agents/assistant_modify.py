import time
from pathlib import Path

from openai import OpenAI

from sweepai.config.server import OPENAI_API_KEY

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
"""

if __name__ == "__main__":
    client = OpenAI(api_key=OPENAI_API_KEY)
    request = "Add type hints to this file."
    file_object = client.files.create(
        file=Path("sweepai/agents/complete_code.py"), purpose="assistants"
    )
    assistant = client.beta.assistants.create(
        name="Python Modification Assistant",
        instructions=system_message.format(user_request=request),
        tools=[{"type": "code_interpreter"}],
        model="gpt-4-1106-preview",
        file_ids=[file_object.id],
    )
    thread = client.beta.threads.create()
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )
    for _ in range(1200):
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run.status == "completed":
            break
        print(run.status)
        messages = client.beta.threads.messages.list(
            thread_id=thread.id,
        )
        if messages.data:
            print(messages.data[0])
        time.sleep(3)
    messages = client.beta.threads.messages.list(
        thread_id=thread.id,
    )
    file_object = messages.data[0].file_ids[0]
    file_content = client.files.content(file_id=file_object).content.decode("utf-8")
