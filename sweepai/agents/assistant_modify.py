import os
from pathlib import Path
import re
import traceback
import uuid

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
# First read and load the helper functions into the current context. This will allow us to use the helper functions in the rest of the code.
helper_methods_path = '/mnt/data/{file_id}'
with open(helper_methods_path, 'r') as f:
    helper_methods = f.read()
print(helper_methods)
exec(helper_methods)
```

Use the helper functions to identify the minimum set of lines of code we should modify.

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

# @file_cache(ignore_params=["file_path", "chat_logger"])
def new_modify(
    request: str,
    file_path: str,
    file_contents: str,
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
        if not any(file_path.endswith(ext) for ext in allowed_exts):
            os.rename(file_path, file_path + ".txt")
            file_path += ".txt"
        target_file_object = client.files.create(file=Path(file_path), purpose="assistants")
        target_file_id = target_file_object.id
        formatted_helper_method_contents = helper_methods_contents.format(target_file_id=f"/mnt/data/{target_file_id}")
        tmp_helper_file_path = f'/tmp/helper_{uuid.uuid4()}.py'
        with open(tmp_helper_file_path, 'w') as f:
            f.write(formatted_helper_method_contents)
        helper_methods_file_id = client.files.create(file=Path(tmp_helper_file_path), purpose="assistants").id
        os.remove(tmp_helper_file_path)
        uploaded_file_ids = [target_file_id, helper_methods_file_id]
        response = openai_assistant_call(
            request=request,
            instructions=instructions_message.format(file_id=helper_methods_file_id),
            additional_messages=additional_messages,
            uploaded_file_ids=uploaded_file_ids,
            chat_logger=chat_logger,
            assistant_id=assistant_id,
            assistant_name="Code Modification Assistant",
        )
        messages = response.messages
        final_diff = None
        final_diff_pattern = r"<final_diff>\n(.*?)</final_diff>"
        try:
            # try to get the patch
            steps = client.beta.threads.runs.steps.list(run_id=response.run_id, thread_id=response.thread_id)
            all_code_interpreter_outputs = []
            for step in steps.data:
                if step.type == "tool_calls":
                    code_interpreter = step.step_details.tool_calls[0].code_interpreter
                    if code_interpreter and code_interpreter.outputs and code_interpreter.outputs[0].logs:
                        all_code_interpreter_outputs.append(code_interpreter.outputs[0].logs)
            for output in all_code_interpreter_outputs:
                if final_diff_match := re.search(final_diff_pattern, output, re.DOTALL):
                    final_diff = final_diff_match.group(1)
                    return apply_patch(file_contents, final_diff)
            else:
                raise AssistantRaisedException(
                    f"Assistant never provided a final_diff. Here is the last message: {messages.data[0].content[0].text.value}"
                )
        except Exception as e:
            logger.warning(e)
            run = client.beta.threads.runs.create(
                thread_id=response.thread_id,
                assistant_id=response.assistant_id,
                instructions="A valid final_diff was not provided. Please start from the beginning, until the final step. At the end run print_diff(current_content, final_diff=True) to provide a valid final_diff.",
            )
            messages = run_until_complete(
                thread_id=response.thread_id,
                run_id=run.id,
                assistant_id=response.assistant_id,
            )
            try:
                steps = client.beta.threads.runs.steps.list(run_id=run.id, thread_id=response.thread_id)
                all_code_interpreter_outputs = []
                for step in steps.data:
                    if step.type == "tool_calls":
                        code_interpreter = step.step_details.tool_calls[0].code_interpreter
                        if code_interpreter and code_interpreter.outputs and code_interpreter.outputs[0].logs:
                            all_code_interpreter_outputs.append(code_interpreter.outputs[0].logs)
                for output in all_code_interpreter_outputs:
                    if final_diff_match := re.search(final_diff_pattern, output, re.DOTALL):
                        final_diff = final_diff_match.group(1)
                        return apply_patch(file_contents, final_diff)
            except Exception:
                raise AssistantRaisedException(
                    f"Assistant never provided a final_diff. Here is the last message: {messages.data[0].content[0].text.value}"
                )
        try:
            client.files.delete(target_file_id)
            client.files.delete(helper_methods_file_id)
        except:
            pass
    except AssistantRaisedException as e:
        discord_log_error(
            str(e)
            + "\n\n"
            + traceback.format_exc()
            + "\n\n"
            + str(chat_logger.data if chat_logger else "")
        )
        # raise e
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
    response = new_modify(
        instructions,
        "sweepai/utils/ticket_utils.py",
        file_contents=open("sweepai/utils/ticket_utils.py", "r").read(),
        chat_logger=ChatLogger({"username": "kevinlu1248"}),
        additional_messages=additional_messages,
    )
    import pdb; pdb.set_trace()