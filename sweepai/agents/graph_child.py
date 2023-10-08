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
        if "=" in line or line.lstrip().startswith(("class ", "def ")):
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


if __name__ == "__main__":
    file = r'''
import re
from dataclasses import dataclass

from fuzzywuzzy import fuzz
from tqdm import tqdm

from sweepai.logn import logger


def score_line(str1: str, str2: str) -> float:
    if str1 == str2:
        return 100

    if str1.lstrip() == str2.lstrip():
        whitespace_ratio = abs(len(str1) - len(str2)) / (len(str1) + len(str2))
        score = 90 - whitespace_ratio * 10
        return max(score, 0)

    if str1.strip() == str2.strip():
        whitespace_ratio = abs(len(str1) - len(str2)) / (len(str1) + len(str2))
        score = 80 - whitespace_ratio * 10
        return max(score, 0)

    levenshtein_ratio = fuzz.ratio(str1, str2)

    score = 70 * (levenshtein_ratio / 100)
    return max(score, 0)


def match_without_whitespace(str1: str, str2: str) -> bool:
    return str1.strip() == str2.strip()


def line_cost(line: str) -> float:
    if line.strip() == "":
        return 50
    if line.strip().startswith("#") or line.strip().startswith("//"):
        return 50 + len(line) / (len(line) + 1) * 30
    return len(line) / (len(line) + 1) * 100


def score_multiline(query: list[str], target: list[str]) -> float:
    # TODO: add weighting on first and last lines

    q, t = 0, 0  # indices for query and target
    scores: list[tuple[float, float]] = []
    skipped_comments = 0

    def get_weight(q: int) -> float:
        # Prefers lines at beginning and end of query
        # Sequence: 1, 2/3, 1/2, 2/5...
        index = min(q, len(query) - q)
        return 100 / (index / 2 + 1)

    while q < len(query) and t < len(target):
        q_line = query[q]
        t_line = target[t]
        weight = get_weight(q)

        if match_without_whitespace(q_line, t_line):
            # Case 1: lines match
            scores.append((score_line(q_line, t_line), weight))
            q += 1
            t += 1
        elif "..." in q_line:
            # Case 3: ellipsis wildcard
            t += 1
            if q + 1 == len(query):
                scores.append((100 - (len(target) - t), weight))
                q += 1
                t = len(target)
                break
            max_score = 0
            # Radix optimization
            indices = [
                t + i
                for i, line in enumerate(target[t:])
                if match_without_whitespace(line, query[q + 1])
            ]
            if not indices:
                # logger.warning(f"Could not find whitespace match, using brute force")
                indices = range(t, len(target))
            for i in indices:
                score, weight = score_multiline(query[q + 1 :], target[i:]), (
                    100 - (i - t) / len(target) * 10
                )
                new_scores = scores + [(score, weight)]
                total_score = sum(
                    [value * weight for value, weight in new_scores]
                ) / sum([weight for _, weight in new_scores])
                max_score = max(max_score, total_score)
            return max_score
        elif (
            t_line.strip() == ""
            or t_line.strip().startswith("#")
            or t_line.strip().startswith("//")
        ):
            # Case 2: skipped comment
            skipped_comments += 1
            t += 1
            scores.append((90, weight))
        else:
            break

    if q < len(query):
        scores.extend(
            (100 - line_cost(line), get_weight(index))
            for index, line in enumerate(query[q:])
        )
    if t < len(target):
        scores.extend(
            (100 - line_cost(line), 100) for index, line in enumerate(target[t:])
        )

    final_score = (
        sum([value * weight for value, weight in scores])
        / sum([weight for _, weight in scores])
        if scores
        else 0
    )
    final_score *= 1 - 0.05 * skipped_comments

    return final_score


@dataclass
class Match:
    start: int
    end: int
    score: float
    indent: str = ""

    def __gt__(self, other):
        return self.score > other.score


def get_indent_type(content: str):
    two_spaces = len(re.findall(r"\n {2}[^ ]", content))
    four_spaces = len(re.findall(r"\n {4}[^ ]", content))

    return "  " if two_spaces > four_spaces else "    "


def get_max_indent(content: str, indent_type: str):
    return max(len(line) - len(line.lstrip()) for line in content.split("\n")) // len(
        indent_type
    )


def find_best_match(query: str, code_file: str):
    best_match = Match(-1, -1, 0)

    code_file_lines = code_file.split("\n")
    query_lines = query.split("\n")
    if len(query_lines) > 0 and query_lines[-1].strip() == "...":
        query_lines = query_lines[:-1]
    if len(query_lines) > 0 and query_lines[0].strip() == "...":
        query_lines = query_lines[1:]
    indent = get_indent_type(code_file)
    max_indents = get_max_indent(code_file, indent)

    top_matches = []

    if len(query_lines) == 1:
        for i, line in enumerate(code_file_lines):
            score = score_line(line, query_lines[0])
            if score > best_match.score:
                best_match = Match(i, i + 1, score)
        return best_match

    for num_indents in range(0, min(max_indents + 1, 20)):
        indented_query_lines = [indent * num_indents + line for line in query_lines]

        start_indices = [
            i
            for i, line in enumerate(code_file_lines)
            if score_line(line, indented_query_lines[0]) > 50
        ]
        start_indices = start_indices or [
            i
            for i in start_indices
            if score_multiline(indented_query_lines[:2], code_file_lines[i : i + 2])
            > 50
        ]

        if not start_indices:
            start_pairs = [
                (i, score_line(line, indented_query_lines[0]))
                for i, line in enumerate(code_file_lines)
            ]
            start_pairs.sort(key=lambda x: x[1], reverse=True)
            start_pairs = start_pairs[: min(40, len(start_pairs) // 5)]
            start_indices = sorted([i for i, _ in start_pairs])

        for i in tqdm(
            start_indices,
            position=0,
            desc=f"Indent {num_indents}/{max_indents}",
            leave=False,
        ):
            end_indices = [
                j
                for j, line in enumerate(code_file_lines[i:], start=i)
                if score_line(line, indented_query_lines[-1]) > 50
            ]
            end_indices = end_indices or [
                j
                for j in end_indices
                if score_multiline(
                    indented_query_lines[-2:], code_file_lines[i + j - 1 : i + j + 1]
                )
                > 50
            ]  # sus code
            if not end_indices:
                end_pairs = [
                    (j, score_line(line, indented_query_lines[-1]))
                    for j, line in enumerate(code_file_lines[i:], start=i)
                ]
                end_pairs.sort(key=lambda x: x[1], reverse=True)
                end_pairs = end_pairs[: min(40, len(end_pairs) // 5)]
                end_indices = sorted([j for j, _ in end_pairs])

            for j in tqdm(
                end_indices, position=1, leave=False, desc=f"Starting line {i}"
            ):
                candidate = code_file_lines[i : j + 1]
                raw_score = score_multiline(indented_query_lines, candidate)

                score = raw_score * (1 - num_indents * 0.01)
                current_match = Match(i, j + 1, score, indent * num_indents)

                if raw_score >= 99.99:  # early exit, 99.99 for floating point error
                    logger.info(f"Exact match found! Returning: {current_match}")
                    return current_match

                top_matches.append(current_match)

                if score > best_match.score:
                    best_match = current_match

    unique_top_matches: list[Match] = []
    print(unique_top_matches)
    unique_spans = set()
    for top_match in sorted(top_matches, reverse=True):
        if (top_match.start, top_match.end) not in unique_spans:
            unique_top_matches.append(top_match)
            unique_spans.add((top_match.start, top_match.end))
    for top_match in unique_top_matches[:5]:
        logger.print(top_match)

    # Todo: on_comment file comments able to modify multiple files
    return unique_top_matches[0] if unique_top_matches else Match(-1, -1, 0)


def split_ellipses(query: str) -> list[str]:
    queries = []
    current_query = ""
    for line in query.split("\n"):
        if line.strip() == "...":
            queries.append(current_query.strip("\n"))
            current_query = ""
        else:
            current_query += line + "\n"
    return queries


test_code = """\
capture_posthog_event(username, "started", properties=metadata)
...
capture_posthog_event(
    username,
    "failed",
    properties={"error": str(e), "reason": "Failed to get files", **metadata},
)
...
capture_posthog_event(
    username,
    "failed",
    properties={
        "error": "No files to change",
        "reason": "No files to change",
        **metadata,
    },
)
...
capture_posthog_event(
    username,
    "failed",
    properties={
        "error": str(e),
        "reason": "Failed to make changes",
        **metadata,
    },
)
...
capture_posthog_event(username, "success", properties={**metadata})
"""
'''

    print(extract_int("10, 10-11 (message)"))
    print("\nExtracting Span:")
    span = extract_python_span(file, ["find_best_match", "__gt__"]).content
    print(span)
    quit()

    # test response for plan
    response = """<code_analysis>
The issue requires moving the is_python_issue bool in sweep_bot to the on_ticket.py flow. The is_python_issue bool is used in the get_files_to_change function in sweep_bot.py to determine if the issue is related to a Python file. This information is then logged and used to generate a plan for the relevant snippets.

In the on_ticket.py file, the get_files_to_change function is called, but the is_python_issue bool is not currently used or logged. The issue also requires using the metadata in on_ticket to log this event to posthog, which is a platform for product analytics.

The posthog.capture function is used in on_ticket.py to log events with specific properties. The properties include various metadata about the issue and the user. The issue requires passing the is_python_issue bool to get_files_to_change and then logging this as an event to posthog.
</code_analysis>

<relevant_new_snippet>
sweepai/handlers/on_ticket.py:590-618
</relevant_new_snippet>

<code_change_description file_path="sweepai/handlers/on_ticket.py">
First, you need to modify the get_files_to_change function call in on_ticket.py to pass the is_python_issue bool. You can do this by adding an argument to the function call at line 690. The argument should be a key-value pair where the key is 'is_python_issue' and the value is the is_python_issue bool.

Next, you need to log the is_python_issue bool as an event to posthog. You can do this by adding a new posthog.capture function call after the get_files_to_change function call. The first argument to posthog.capture should be 'username', the second argument should be a string describing the event (for example, 'is_python_issue'), and the third argument should be a dictionary with the properties to log. The properties should include 'is_python_issue' and its value.

Here is an example of how to make these changes:

```python
# Add is_python_issue to get_files_to_change function call
file_change_requests, plan = sweep_bot.get_files_to_change(is_python_issue=is_python_issue)

# Log is_python_issue to posthog
posthog.capture(username, 'is_python_issue', properties={'is_python_issue': is_python_issue})
```
Please replace 'is_python_issue' with the actual value of the bool.
</code_change_description>"""
    gc_and_plan = GraphContextAndPlan.from_string(
        response, "sweepai/handlers/on_ticket.py"
    )
    # print(gc_and_plan.code_change_description)
