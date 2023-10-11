import re

from tree_sitter_languages import get_parser

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import RegexMatchableBaseModel, Snippet
from sweepai.logn import logger

system_prompt = """You are a genius engineer tasked with extracting the code and planning the solution to the following GitHub issue.
Decide whether the file_path {file_path} needs to be modified to solve this issue and the proposed solution.

First determine whether changes in file_path are necessary.
Then, if code changes need to be made in file_path, extract the relevant_new_snippets and write the code_change_description.
In code_change_description, mention each relevant_new_snippet and how to modify it.

1. Analyze the code and extract the relevant_new_snippets.
Extract only the relevant_new_snippets that allow us to write code_change_description for file_path.

<code_analysis file_path=\"{file_path}\">
{{thought about potentially relevant snippet and its relevance to the issue}}
...
</code_analysis>

<relevant_new_snippets>
{{relevant snippet from \"{file_path}\" in the format file_path:start_idx-end_idx. Do not delete any relevant entities.}}
...
</relevant_new_snippets>

2. Generate a code_change_description for \"{file_path}\".
When writing the plan for code changes to \"{file_path}\" keep in mind the user will read the metadata and the relevant_new_snippets.

<code_change_description file_path=\"{file_path}\">
{{The changes are constrained to the file_path and code mentioned in file_path.
These are clear and detailed natural language descriptions of modifications to be made in file_path.
The relevant_snippets_in_repo are read-only.}}
</code_change_description>"""

NO_MODS_KWD = "#NONE"

graph_user_prompt = (
    """\
<READONLY>
<issue_metadata>
{issue_metadata}
</issue_metadata>
{previous_snippets}

<all_symbols_and_files>
{all_symbols_and_files}</all_symbols_and_files>
</READONLY>

<file_path=\"{file_path}\" entities=\"{entities}\">
{code}
</file_path>

Provide the relevant_new_snippets and code_change_description to the file_path above.
If there are no relevant_new_snippets or code_change_description, end your message with """
    + NO_MODS_KWD
)


class GraphContextAndPlan(RegexMatchableBaseModel):
    relevant_new_snippet: list[Snippet]
    code_change_description: str | None
    file_path: str
    entities: str = None

    @classmethod
    def from_string(cls, string: str, file_path: str, **kwargs):
        snippets_pattern = r"""<relevant_new_snippets.*?>(\n)?(?P<relevant_new_snippet>.*)</relevant_new_snippets>"""
        plan_pattern = r"""<code_change_description.*?>(\n)?(?P<code_change_description>.*)</code_change_description>"""
        snippets_match = re.search(snippets_pattern, string, re.DOTALL)
        relevant_new_snippet_match = None
        code_change_description = ""
        relevant_new_snippet = []
        if not snippets_match:
            return cls(
                relevant_new_snippet=relevant_new_snippet,
                code_change_description=code_change_description,
                file_path=file_path,
                **kwargs,
            )
        relevant_new_snippet_match = snippets_match.group("relevant_new_snippet")
        for raw_snippet in relevant_new_snippet_match.strip().split("\n"):
            if raw_snippet.strip() == NO_MODS_KWD:
                continue
            if ":" not in raw_snippet:
                continue
            generated_file_path, lines = (
                raw_snippet.split(":")[-2],
                raw_snippet.split(":")[-1],
            )  # solves issue with file_path:snippet:line1-line2
            if not generated_file_path or not lines.strip():
                continue
            generated_file_path, lines = (
                generated_file_path.strip(),
                lines.split()[0].strip(),
            )  # second one accounts for trailing text like "1-10 (message)"
            if generated_file_path != file_path:
                continue
            if "-" not in lines:
                continue
            start, end = lines.split("-", 1)
            start, end = extract_int(start), extract_int(end)
            if start is None or end is None:
                continue
            start = int(start)
            end = int(end) - 1
            end = min(end, start + 200)
            if end - start < 20:  # don't allow small snippets
                start = start - 10
                end = start + 10
            snippet = Snippet(file_path=file_path, start=start, end=end, content="")
            relevant_new_snippet.append(snippet)
        plan_match = re.search(plan_pattern, string, re.DOTALL)
        if plan_match:
            code_change_description = plan_match.group(
                "code_change_description"
            ).strip()
            if code_change_description.endswith(NO_MODS_KWD):
                logger.warning(
                    "NO_MODS_KWD found in code_change_description for " + file_path
                )
                code_change_description = None
        return cls(
            relevant_new_snippet=relevant_new_snippet,
            code_change_description=code_change_description,
            file_path=file_path,
            **kwargs,
        )

    def __str__(self) -> str:
        return f"{self.relevant_new_snippet}\n{self.code_change_description}"


class GraphChildBot(ChatGPT):
    def code_plan_extraction(
        self,
        code,
        file_path,
        entities,
        issue_metadata,
        previous_snippets,
        all_symbols_and_files,
    ) -> GraphContextAndPlan:
        if not entities:
            return GraphContextAndPlan(
                relevant_new_snippet=Snippet(file_path="", start=0, end=0, content=code),
                code_change_description="",
                file_path=file_path,
            )
        python_snippet = extract_python_span(code, entities)
        python_snippet.file_path = file_path
        return GraphContextAndPlan(
            relevant_new_snippet=[python_snippet],
            code_change_description="",
            file_path=file_path,
        )


def extract_int(s):
    match = re.search(r"\d+", s)
    if match:
        return int(match.group())
    return None


def extract_python_span(code: str, entities: str):
    lines = code.split("\n")

    # Identify lines where entities are declared as variables
    variables_with_entity = set()
    lines_with_entity = set()
    for i, line in enumerate(lines):
        for entity in entities:
            if (
                entity in line
                and "=" in line
                and not line.lstrip().startswith(("class ", "def "))
            ):
                variable_name = line.split("=")[0].strip()
                if not variable_name.rstrip().endswith(")"):
                    variables_with_entity.add(variable_name)
                    lines_with_entity.add(i)

    captured_lines = set()

    # Up to the first variable definition
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("class ", "def ")):
            break
    captured_lines.update(range(i))

    parser = get_parser("python")
    tree = parser.parse(code.encode("utf-8"))

    def walk_tree(node):
        if node.type in ["class_definition", "function_definition"]:
            # Check if the entity is in the first line (class Entity or class Class(Entity), etc)
            start_line, end_line = node.start_point[0], node.end_point[0]
            if (
                any(start_line <= line_no <= end_line for line_no in lines_with_entity)
                and node.type == "function_definition"
                and end_line - start_line < 100
            ):
                captured_lines.update(range(start_line, end_line + 1))
            if any(
                entity in node.text.decode("utf-8").split("\n")[0]
                for entity in entities
            ):
                captured_lines.update(range(start_line, end_line + 1))
        for child in node.children:
            walk_tree(child)

    try:
        walk_tree(tree.root_node)
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(e)
        logger.error("Failed to parse python file. Using for loop instead.")
        # Haven't tested this section

        # Capture entire subscope for class and function definitions
        for i, line in enumerate(lines):
            if any(
                entity in line and line.lstrip().startswith(keyword)
                for entity in entities
                for keyword in ["class ", "def "]
            ):
                indent_level = len(line) - len(line.lstrip())
                captured_lines.add(i)

                # Add subsequent lines until a line with a lower indent level is encountered
                j = i + 1
                while j < len(lines):
                    current_indent = len(lines[j]) - len(lines[j].lstrip())
                    if current_indent > indent_level and len(lines[j].lstrip()) > 0:
                        captured_lines.add(j)
                        j += 1
                    else:
                        break
            # For non-variable lines with the entity, capture ±20 lines
            elif any(entity in line for entity in entities):
                captured_lines.update(range(max(0, i - 20), min(len(lines), i + 21)))

    captured_lines_list = sorted(list(captured_lines))
    result = []

    # Coalesce lines that are close together
    coalesce = 5
    for i in captured_lines_list:
        if i + coalesce in captured_lines_list and any(
            i + j not in captured_lines for j in range(1, coalesce)
        ):
            captured_lines.update(range(i, i + coalesce))

    captured_lines_list = sorted(list(captured_lines))

    previous_line_number = -1  # Initialized to an impossible value

    # Construct the result with line numbers and mentions
    for i in captured_lines_list:
        line = lines[i]

        if previous_line_number != -1 and i - previous_line_number > 1:
            result.append("...\n")

        result.append(line)

        previous_line_number = i

    return Snippet(file_path="", start=0, end=0, content="\n".join(result))



#     # test response for plan
#     response = """<code_analysis>
# The issue requires moving the is_python_issue bool in sweep_bot to the on_ticket.py flow. The is_python_issue bool is used in the get_files_to_change function in sweep_bot.py to determine if the issue is related to a Python file. This information is then logged and used to generate a plan for the relevant snippets.

# In the on_ticket.py file, the get_files_to_change function is called, but the is_python_issue bool is not currently used or logged. The issue also requires using the metadata in on_ticket to log this event to posthog, which is a platform for product analytics.

# The posthog.capture function is used in on_ticket.py to log events with specific properties. The properties include various metadata about the issue and the user. The issue requires passing the is_python_issue bool to get_files_to_change and then logging this as an event to posthog.
# </code_analysis>

# <relevant_new_snippet>
# sweepai/handlers/on_ticket.py:590-618
# </relevant_new_snippet>

# <code_change_description file_path="sweepai/handlers/on_ticket.py">
# First, you need to modify the get_files_to_change function call in on_ticket.py to pass the is_python_issue bool. You can do this by adding an argument to the function call at line 690. The argument should be a key-value pair where the key is 'is_python_issue' and the value is the is_python_issue bool.

# Next, you need to log the is_python_issue bool as an event to posthog. You can do this by adding a new posthog.capture function call after the get_files_to_change function call. The first argument to posthog.capture should be 'username', the second argument should be a string describing the event (for example, 'is_python_issue'), and the third argument should be a dictionary with the properties to log. The properties should include 'is_python_issue' and its value.

# Here is an example of how to make these changes:

# ```python
# # Add is_python_issue to get_files_to_change function call
# file_change_requests, plan = sweep_bot.get_files_to_change(is_python_issue=is_python_issue)

# # Log is_python_issue to posthog
# posthog.capture(username, 'is_python_issue', properties={'is_python_issue': is_python_issue})
# ```
# Please replace 'is_python_issue' with the actual value of the bool.
# </code_change_description>"""
#     gc_and_plan = GraphContextAndPlan.from_string(
#         response, "sweepai/handlers/on_ticket.py"
#     )
#     # print(gc_and_plan.code_change_description)
