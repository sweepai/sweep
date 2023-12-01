import traceback

from loguru import logger

from sweepai.agents.assistant_wrapper import (
    client,
    openai_assistant_call,
    run_until_complete,
)
from sweepai.core.entities import AssistantRaisedException, Message
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error


# TODO: move these to helper functions
long_file_helper_functions = r"""def print_original_lines(i, j):
    \"\"\"
    Displays the original lines between line numbers i and j.
    \"\"\"
    start = max(0, i - 10)
    end = min(len(original_lines), j + 10)

    for index in range(start, end):
        if index == i:
            print("\n--- Start of snippet ---")
        elif index == j:
            print("--- End of snippet ---\n")

        print(f"{{index}}: {{original_lines[index]}}")
    print("\n")

def print_original_lines_with_keywords(keywords):
    \"\"\"
    Displays the original lines between line numbers i and j when any of the keywords are found.
    Use single words.
    \"\"\"
    context = 10

    matches = [i for i, line in enumerate(original_lines) if any(keyword in line.lower() for keyword in keywords)]
    expanded_matches = set()

    for match in matches:
        start = max(0, match - context)
        end = min(len(original_lines), match + context + 1)
        for i in range(start, end):
            expanded_matches.add(i)

    for i in sorted(expanded_matches):
        print(f"{{i}}: {{original_lines[i]}}")"""


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

system_message = r"""You're an engineer assigned to make an edit to solve a GitHub issue. Modify the attached file to complete the task by writing Python code to read and make edits to the file.

# Guide
## Step 1: Setup Helper Functions and Identify Relevant Lines
First instantiate and run all of the following code. Then identify the relevant lines by running `print_original_lines` and `print_original_lines_with_keywords`:

### HELPER FUNCTIONS TO RUN
```python
import ast
import difflib

{helper_functions}

def check_valid_python(code):
    \"\"\"
    Check if the code is valid python using ast.parse. Use this to check if python code is valid after making edits.
    \"\"\"
    import ast
    try:
        # Check for valid python
        ast.parse(code)
        print("Python code is valid.")
    except SyntaxError as e:
        print("SyntaxError:", e)

def print_diff(new_content, old_content=file_content):
    import difflib
    print(difflib.unified_diff(
        file_content, current_content
    ))

def set_indentation(code, indent_size=4):
    \"\"\"
    Set the indentation of the code to indent_size.
    Use this to programmatically indent code that is not indented properly.
    \"\"\"
    lines = [line for line in code.split('\n') if line.strip()]
    min_indent = min(len(line) - len(line.lstrip()) for line in lines)
    return '\n'.join(' ' * indent_size + line[min_indent:] for line in lines)

file_path = '/mnt/data/file-example_file'
with open(file_path, 'r') as file:
    file_content = file.read()
original_lines = file_content.splitlines()
current_content = file_content # this will be used later
```

Use the helper functions to identify the minimal set of lines of code we should modify.

## Step 2: Iterative Code Modification
You will iteratively make small edits. Before making each edit, make a backup of the current_content by running:

```python
prev_content = current_content
```

### Modification script
Modify fewer lines of code if possible, as this reduces the chance of mistakes.
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
If the change is bad you can revert it by running and then try making the change again:

```python
current_content = prev_content
# then try making the change again
```

Move to Step 3 once all the edits are completed.

## Step 3: Output
Perform a final review once all edits from Step 2 are completed. Use the following code:

```python
print(current_content)
check_valid_python(current_content)
print_diff(current_content)
```

Once you are done, save the output to a new file and attach it as part of your message response."""

@file_cache(ignore_params=["file_path", "chat_logger"])
def new_modify(
    request: str,
    file_path: str,
    additional_messages: list[Message] = [],
    chat_logger: ChatLogger | None = None,
    assistant_id: str = "asst_SgttsEvgZWJBc0mbnHkJe1pE",
    start_line: int = -1,
    end_line: int = -1,
):
    try:
        file_content = open(file_path, "r").read()
        if start_line > 0 and end_line > 0:
            request += (
                f"\n\nThe relevant lines are between {start_line} and {end_line}.\n\n"
            )
        request = f"This is the file:\n{file_content}\n" + f"# Instructions:\n{request}"
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
            assistant_name="Code Modification Assistant",
        )
        messages = response.messages
        file_id = None
        try:
            file_id = messages.data[0].file_ids[0]
        except Exception as e:
            logger.warning(e)
            run = client.beta.threads.runs.create(
                thread_id=response.thread_id,
                assistant_id=response.assistant_id,
                instructions="Give me the newly generated file as part of your output response's file_ids. Do not provide a link.",
            )
            messages = run_until_complete(
                thread_id=response.thread_id,
                run_id=run.id,
                assistant_id=response.assistant_id,
            )
            try:
                file_id = messages.data[0].file_ids[0]
            except Exception:
                # raise AssistantRaisedException(
                #     f"Assistant never provided a file. Here is the last message: {messages.data[0].content[0].text.value}"
                # )
                pass
        file_content = client.files.content(file_id=file_id).content.decode("utf-8")
        # delete the generated file afterwards
        if file_id: client.files.delete(file_id=file_id)
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

if __name__ == "__main__":
    instructions = """• Instantiate `FilterAgent` and invoke `filter_search_query` with the query before the lexical search is performed.
• Capture the filtered query and replace the initial query with this new filtered version.
• Add error handling for the integration with `FilterAgent`."""

    additional_messages = [Message(role='user', content='# Repo & Issue Metadata\nRepo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.\nIssue Title: create a new agent to be used in ticket_utils.py\nIssue Description: ### Details\n\nThe agent should filter unnecessary terms out of the search query to be sent into lexical search. Use a prompt to do this, using name_agent.py as a reference', name=None, function_call=None, key='issue_metadata'), Message(role='user', content='We have previously changed these files:\n<changed_file file_path="sweepai/agents/filter_agent.py">\n--- \n+++ \n@@ -0,0 +1,35 @@\n+import re\n+\n+from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL\n+from sweepai.core.chat import ChatGPT\n+\n+prompt = """\\\n+<original_query>\n+{original_query}\n+</original_query>\n+Filter out unnecessary terms from the above search query and generate a new search query that is optimized for a lexical search.\n+<filtered_query>\n+filtered_query\n+</filtered_query>\n+"""\n+\n+class FilterAgent(ChatGPT):\n+    def filter_search_query(\n+        self,\n+        original_query,\n+        chat_logger=None,\n+    ):\n+        self.model = (\n+            DEFAULT_GPT4_32K_MODEL\n+            if (chat_logger and chat_logger.is_paying_user())\n+            else DEFAULT_GPT35_MODEL\n+        )\n+        filter_response = self.chat(\n+            content=prompt.format(\n+                original_query=original_query,\n+            ),\n+        )\n+        filter_pattern = r"<filtered_query>\\n(.*?)\\n</filtered_query>"\n+        filter_match = re.search(filter_pattern, filter_response, re.DOTALL)\n+        filtered_query = filter_match.group(1).strip().strip(\'"\').strip("\'").strip("`")\n+        return filtered_query\n</changed_file>\n<changed_file file_path="sweepai/agents/filter_agent_test.py">\n--- \n+++ \n@@ -0,0 +1,22 @@\n+import pytest\n+\n+from sweepai.agents.filter_agent import FilterAgent\n+\n+\n+def test_filter_search_query():\n+    filter_agent = FilterAgent()\n+\n+    # Test with empty string\n+    original_query = ""\n+    expected_output = ""\n+    assert filter_agent.filter_search_query(original_query) == expected_output\n+\n+    # Test with string containing only unnecessary terms\n+    original_query = "the and or"\n+    expected_output = ""\n+    assert filter_agent.filter_search_query(original_query) == expected_output\n+\n+    # Test with string containing a mix of necessary and unnecessary terms\n+    original_query = "the quick brown fox"\n+    expected_output = "quick brown fox"\n+    assert filter_agent.filter_search_query(original_query) == expected_output\n</changed_file>', name=None, function_call=None, key='changed_files_summary')]

    # for use in playground
    first_additional_message = """# Repo & Issue Metadata
Repo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.
Issue Title: create a new agent to be used in ticket_utils.py
Issue Description: ### Details

The agent should filter unnecessary terms out of the search query to be sent into lexical search. Use a prompt to do this, using name_agent.py as a reference"""

    response = new_modify(
        instructions,
        "sweepai/utils/ticket_utils.py",
        chat_logger=ChatLogger({"username": "kevinlu1248"}),
        additional_messages=additional_messages,
    )
    import pdb; pdb.set_trace()