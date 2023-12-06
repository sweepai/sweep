from sweepai.agents.assistant_modify import new_modify
from sweepai.core.entities import Message
from sweepai.utils.chat_logger import ChatLogger

### Benchmark 1: Integration

instructions = """• Instantiate `FilterAgent` and invoke `filter_search_query` with the query before the lexical search is performed.
• Capture the filtered query and replace the initial query with this new filtered version.
• Add error handling for the integration with `FilterAgent`."""

additional_messages = [
    Message(
        role="user",
        content="# Repo & Issue Metadata\nRepo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.\nIssue Title: create a new agent to be used in ticket_utils.py\nIssue Description: ### Details\n\nThe agent should filter unnecessary terms out of the search query to be sent into lexical search. Use a prompt to do this, using name_agent.py as a reference",
        name=None,
        function_call=None,
        key="issue_metadata",
    ),
    Message(
        role="user",
        content='We have previously changed these files:\n<changed_file file_path="sweepai/agents/filter_agent.py">\n--- \n+++ \n@@ -0,0 +1,35 @@\n+import re\n+\n+from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL\n+from sweepai.core.chat import ChatGPT\n+\n+prompt = """\\\n+<original_query>\n+{original_query}\n+</original_query>\n+Filter out unnecessary terms from the above search query and generate a new search query that is optimized for a lexical search.\n+<filtered_query>\n+filtered_query\n+</filtered_query>\n+"""\n+\n+class FilterAgent(ChatGPT):\n+    def filter_search_query(\n+        self,\n+        original_query,\n+        chat_logger=None,\n+    ):\n+        self.model = (\n+            DEFAULT_GPT4_32K_MODEL\n+            if (chat_logger and chat_logger.is_paying_user())\n+            else DEFAULT_GPT35_MODEL\n+        )\n+        filter_response = self.chat(\n+            content=prompt.format(\n+                original_query=original_query,\n+            ),\n+        )\n+        filter_pattern = r"<filtered_query>\\n(.*?)\\n</filtered_query>"\n+        filter_match = re.search(filter_pattern, filter_response, re.DOTALL)\n+        filtered_query = filter_match.group(1).strip().strip(\'"\').strip("\'").strip("`")\n+        return filtered_query\n</changed_file>\n<changed_file file_path="sweepai/agents/filter_agent_test.py">\n--- \n+++ \n@@ -0,0 +1,22 @@\n+import pytest\n+\n+from sweepai.agents.filter_agent import FilterAgent\n+\n+\n+def test_filter_search_query():\n+    filter_agent = FilterAgent()\n+\n+    # Test with empty string\n+    original_query = ""\n+    expected_output = ""\n+    assert filter_agent.filter_search_query(original_query) == expected_output\n+\n+    # Test with string containing only unnecessary terms\n+    original_query = "the and or"\n+    expected_output = ""\n+    assert filter_agent.filter_search_query(original_query) == expected_output\n+\n+    # Test with string containing a mix of necessary and unnecessary terms\n+    original_query = "the quick brown fox"\n+    expected_output = "quick brown fox"\n+    assert filter_agent.filter_search_query(original_query) == expected_output\n</changed_file>',
        name=None,
        function_call=None,
        key="changed_files_summary",
    ),
]
file_contents = open("sweepai/utils/ticket_utils.py", "r").read()
response = new_modify(
    instructions,
    "sweepai/utils/ticket_utils.py",
    file_contents=file_contents,
    chat_logger=ChatLogger({"username": "kevinlu1248"}),
    additional_messages=additional_messages,
)

### Benchmark 2: Inplace modification
instructions = """• Replace the broken installation link with the provided new link.\n• Change the text from "check out our [tutorial on running Sweep on Docusaurus](https://docs.sweep.dev/tutorial)." \n  to "check out our [tutorial on running Sweep on Docusaurus](https://docs.sweep.dev/usage/tutorial).\""""
additional_messages = [
    Message(
        role="user",
        content="# Repo & Issue Metadata\nRepo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.\nIssue Title: replace the broken installation link in installation.md with https://docs.sweep.dev/usage/tutorial",
        name=None,
        function_call=None,
        key="issue_metadata",
    )
]
file_contents = open("docs/installation.md", "r").read()
response = new_modify(
    instructions,
    "docs/installation.md",
    file_contents=file_contents,
    chat_logger=ChatLogger({"username": "wwzeng1"}),
    additional_messages=additional_messages,
)
