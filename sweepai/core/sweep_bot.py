import os
import re
from typing import Iterator

from loguru import logger
from networkx import Graph


from tqdm import tqdm
from rapidfuzz import fuzz

from sweepai.agents.modify_utils import check_valid_parentheses, contains_ignoring_whitespace, english_join, find_best_match, find_best_matches, find_max_indentation, find_smallest_valid_superspan, get_error_message, indent, set_fcr_change_type
from sweepai.core.annotate_code_openai import get_annotated_source_code
from sweepai.core.chat import ChatGPT, continuous_llm_calls
from sweepai.core.entities import (
    FileChangeRequest,
    Message,
    RegexMatchError,
    Snippet,
)
from sweepai.core.prompts import (
    context_files_to_change_prompt,
    context_files_to_change_system_prompt,
    gha_files_to_change_system_prompt,
    gha_files_to_change_system_prompt_2,
    gha_files_to_change_prompt,
    gha_files_to_change_prompt_2,
    test_files_to_change_system_prompt,
    test_files_to_change_prompt,
    fix_files_to_change_prompt,
    fix_files_to_change_system_prompt,
)
from sweepai.core.planning_prompts import (
    proposed_plan_prompt,
    plan_generation_steps_system_prompt,
    plan_generation_steps_prompt,
    proposed_plan_system_prompt,
    issue_sub_request_prompt,
    issue_sub_request_system_prompt,
    anthropic_rename_prompt,
)
from sweepai.core.on_comment_prompts import (
    issue_sub_request_on_comment_system_prompt,
    on_comment_pr_diffs_format,
    rename_on_comment_prompt,
    rename_on_comment_system_prompt,
    issue_sub_request_on_comment_prompt,
    proposed_plan_on_comment_system_prompt,
    proposed_plan_on_comment_prompt,
    plan_generation_steps_on_comment_system_prompt,
    plan_generation_steps_on_comment_prompt
)
from sweepai.dataclasses.code_suggestions import CodeSuggestion
from sweepai.utils.chat_logger import ChatLogger
# from sweepai.utils.previous_diff_utils import get_relevant_commits
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.str_utils import extract_object_fields_from_string
from sweepai.utils.streamable_functions import streamable

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"
SNIPPET_TOKEN_BUDGET = int(150_000 * 3.5)  # 140k tokens
MAX_SNIPPETS = 15
RELEVANCE_THRESHOLD = 0.125

def to_raw_string(s):
    return repr(s).lstrip("u")[1:-1]


sandbox_error_prompt = """The following error logs were returned from `{command}`. Make changes to the current file so that it passes this CI/CD command.

```
{error_logs}
```

Edit old_code to pass the CI/CD."""

sandbox_error_prompt_test = """The following error logs were returned from `{command}`. Make changes to the current file so that it passes this CI/CD command.

```
{error_logs}
```

Edit old_code to pass the CI/CD.
1. Analyze the business logic and tests. Identify whether the failure is in the unit tests or business logic.
2a. If the business logic is correct fix the test to return the expected output.
2b. If the business logic has a bug or you are unsure, skip the failing tests with an explanation."""

GHA_PROMPT = """You're working on resolving a GitHub issue but the code changes fail the GitHub Actions.

You are trying to resolve the following GitHub issue:
<original_github_issue>
{problem_statement}
</original_github_issue>

You made some changes, but GitHub Actions failed with the following logs:
<github_actions_logs>
{github_actions_logs}
</github_actions_logs>

You have previously made the following changes. The diffs represent the current state of the file/project:
<changes_made>
{changes_made}
</changes_made>

Fix the above GitHub Actions."""

GHA_PROMPT_WITH_HISTORY = """You're working on resolving a GitHub issue but the code changes fail the GitHub Actions.

You are trying to resolve the following GitHub issue:
<original_github_issue>
{problem_statement}
</original_github_issue>

Previously the Githu Actions were failing with these logs:
<previous_github_actions_logs>
{previous_github_actions_logs}
</previous_github_actions_logs>

You made some changes to address the previous Github Action failures, but GitHub Actions are now failing with the following logs:
<current_github_actions_logs>
{current_github_actions_logs}
</current_github_actions_logs>

You have previously made the following changes. The diffs represent the current state of the file/project:
<changes_made>
{changes_made}
</changes_made>

Fix the above GitHub Actions."""

def cleanup_fcrs(fcrs_string: str):
    fcrs_string = re.sub(r"<original_code(?: file_path=\".*?\")?(?: index=\"\d+\")?>", "<original_code>", fcrs_string)
    fcrs_string = re.sub(r"<new_code(?: file_path=\".*?\")?(?: index=\"\d+\")?>", "<new_code>", fcrs_string)
    return fcrs_string

def parse_patch_fcrs(fcr_patch_string: str):
    pattern = re.compile(r"""<(?P<change_type>[a-z_]+)\s+file=\"(?P<filename>[a-zA-Z0-9/\\\.\[\]\(\)\_\+\- @\{\}]*?)\"\s+index=\"(?P<index>\d+)\">(?P<instructions>.*?)\s*<\/\1>""", re.DOTALL)
    drop_pattern = re.compile("<drop>(\d+?)</drop>", re.DOTALL)
    matches = []
    for match in pattern.finditer(fcr_patch_string):
        matches.append((
            int(match.group("index")),
            FileChangeRequest(
                change_type=match.group("change_type"),
                filename=match.group("filename"),
                instructions=match.group("instructions"),
            )
        ))
    drops = [int(drop.group(1).strip()) for drop in drop_pattern.finditer(fcr_patch_string)]
    matches.sort(key=lambda x: x[0])
    return drops, [match for match in matches]

def parse_renames(renames_string: str):
    pattern = re.compile(r"<rename>(.*?)</rename>", re.DOTALL)
    old_name_pattern = re.compile(r"<old_name>(.*?)</old_name>", re.DOTALL)
    new_name_pattern = re.compile(r"<new_name>(.*?)</new_name>", re.DOTALL)
    rename_dict = {}
    for match in pattern.finditer(renames_string):
        rename_match = match.group(1)
        old_name = old_name_pattern.search(rename_match).group(1)
        if not old_name:
            continue
        new_name = new_name_pattern.search(rename_match).group(1)
        if old_name.strip() == new_name.strip():
            continue
        rename_dict[old_name.strip()] = new_name.strip()
    return rename_dict

def remove_line_numbers(s: str) -> str:
    # Check if more than 50% of lines have line numbers
    # Remove line numbers with spaces after (e.g. "1: {code}")
    if len(re.findall(r"\d+?: ", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?: ", "", s, flags=re.MULTILINE)

    # Remove line numbers with no space after (e.g. "112:{code}")
    if len(re.findall(r"\d+?:", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?:", "", s, flags=re.MULTILINE)
    return s

def parse_filenames(text):
    file_names = []
    possible_files = text.split("\n")
    # Regular expression pattern to match file names
    pattern = r'^[^\/.]+(\/[^\/.]+)*\.[^\/.]+$'
    for possible_file in possible_files:
        file_name = possible_file.strip()
        if re.match(pattern, file_name):
            file_names.append(file_name)
    # Find all occurrences of file names in the text
    return file_names

def is_blocked(file_path: str, blocked_dirs: list[str]):
    for blocked_dir in blocked_dirs:
        if file_path.startswith(blocked_dir) and len(blocked_dir) > 0:
            return {"success": True, "path": blocked_dir}
    return {"success": False}

def validate_change(
    code_suggestion: CodeSuggestion,
    cloned_repo: ClonedRepo,
    updated_files: dict[str, dict[str, str]] = {},
    renames_dict: dict[str, str] = {},
    index: int = 0,
    raw_string: str = "",
):
    if not raw_string:
        raw_string = f"<code_changes>\n<original_code>\n{code_suggestion.original_code}\n</original_code>\n<new_code>\n{code_suggestion.new_code}\n</new_code>\n</code_changes>"
    def get_file_contents(file_path):
        if file_path in renames_dict.values():
            file_path = [k for k, v in renames_dict.items() if v == file_path][0]
        if file_path in updated_files:
            return updated_files[file_path]["contents"]
        return cloned_repo.get_file_contents(file_path)
    try:
        file_contents = get_file_contents(code_suggestion.file_path)
    except FileNotFoundError as e:
        for file_path in cloned_repo.get_file_list():
            if file_path.endswith(code_suggestion.file_path):
                logger.info(f"Found similar file {code_suggestion.file_path} at {file_path}")
                file_contents = get_file_contents(file_path)
                code_suggestion.file_path = file_path
        else:
            if code_suggestion.original_code:
                logger.warning(f"Failed to get file contents for {code_suggestion.file_path} due to {e}")
                return f"The file `{code_suggestion.file_path}` does not exist. Double-check your spelling."
    if not code_suggestion.original_code:
        return f"You forgot to provide an <original_code> block. Here is what you provided in the instructions:\n```\n{raw_string}\n```\nIf you would like to drop this task, respond with <drop>{index}</drop>."
    if not code_suggestion.new_code:
        return f"You forgot to a <new_code> block. Here is what you provided in the instructions:\n```\n{raw_string}\n```\nIf you would like to drop this task, respond with <drop>{index}</drop>."
    original_code = code_suggestion.original_code.strip("\n")
    new_code = code_suggestion.new_code.strip("\n")
    if original_code == new_code:
        return f"<original_code> and <new_code> are the same. You must provide a different code snippet in <new_code>. Here is what you provided in the instructions:\n```\n{raw_string}\n```\nIf you would like to drop this task, respond with <drop>{index}</drop>."
    if not original_code:
        return f"The <original_code> can not be empty. If you would like to append code, copy the code you want to append the new code after into the <original_code>, then copy the same code into <new_code>, then finally append the new code after <new_code>. Here is what you provided in the instructions:\n```\n{raw_string}\n```\nIf you would like to drop this task, respond with <drop>{index}</drop>."
    else:
        # if it's present in a previous fcr's new_code, we're not concerned about it
        original_code_in_previous_fcr = False # any(contains_ignoring_whitespace(original_code, fcr["new_code"][0]) for fcr in previous_parsed_fcrs)
        
        # checking previous fcr in original code can lead to false positives if the previous fcr is VERY small and occurs
        # but in practice it doesn't seem likely
        # so we check if the previous fcr comprises > 50% of the original code
        previous_fcr_in_original_code = False
        previous_fcr_occurrences = [] # [contains_ignoring_whitespace(fcr["new_code"][0], original_code) for fcr in previous_parsed_fcrs]

        # check if the previous fcr comprises > 50% of the original code's lines
        # this means that it has a high chance to be valid once the previous diffs are applied
        all_previous_occurrences = [x[1] - x[0] if x else 0 for x in previous_fcr_occurrences]
        if all_previous_occurrences and max(all_previous_occurrences) > len(original_code.splitlines()) // 2:
            previous_fcr_in_original_code = True
        if not contains_ignoring_whitespace(original_code, file_contents) and not original_code_in_previous_fcr and not previous_fcr_in_original_code:
            threshold = 50
            best_match, current_best_score = find_best_match(original_code, file_contents, threshold=threshold, tokenized=True)
            max_indentation = find_max_indentation(file_contents)

            best_score = 0
            best_indent = 0
            for indent_count in range(0, max_indentation, 2):
                match_score = fuzz.ratio(indent(original_code, indent_count), best_match)
                if match_score > best_score:
                    best_score = match_score
                    best_indent = indent_count
            
            too_long_message = f"\nAlso, the <original_code> block you provided is quite long, with {len(original_code.splitlines())} lines of code. Consider isolating <original_code> and <updated_code> to only the section you want to edit to avoid errors copying the code." if len(original_code.splitlines()) > 50 else ""
            ellipses_message = "\nYou must copy code out in full and may not use ellipses, abbreviations, or any short-hand notation in your code." if "# ..." in original_code or "// ..." in original_code else ""

            if not best_match.strip():
                return f"<original_code> does not exist in `{code_suggestion.file_path}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nBut the code is no where to be found in the file. There are also no similar code snippets in this file.{too_long_message}{ellipses_message}"
            if best_score != 100:
                if not check_valid_parentheses(best_match):
                    extended_match = find_smallest_valid_superspan(best_match, file_contents)
                    if extended_match and extended_match.count("\n") - best_match.count('\n') < 20:
                        best_match = extended_match
                if best_score > 80:
                    return f"<original_code> does not exist in `{code_suggestion.file_path}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nDid you mean to modify the following code instead?\n```\n{best_match}\n```\nHere is the diff between your proposed <original_code> and the most similar code in the file:\n```diff\n{generate_diff(indent(original_code, best_indent), best_match, n=10)}\n```{too_long_message}{ellipses_message}"
                else:
                    best_matches = find_best_matches(original_code, file_contents, threshold=threshold, tokenized=True)
                    if len(best_matches) > 1:
                        best_matches_string = "\n\n".join([f"Code match {i}:\n```\n{match_}\n```" for i, (match_, score) in enumerate(best_matches)])
                        return f"<original_code> does not exist in `{code_suggestion.file_path}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nDid you mean to modify one of the following pieces of code instead?\n{best_matches_string}{too_long_message}{ellipses_message}"
                    else:
                        # Same as case > 80
                        return f"<original_code> does not exist in `{code_suggestion.file_path}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nDid you mean to modify the following code instead?\n```\n{best_match}\n```\nHere is the diff between your proposed <original_code> and the most similar code in the file:\n```diff\n{generate_diff(indent(original_code, best_indent), best_match, n=10)}\n```{too_long_message}{ellipses_message}"
        else:
            # Check for parentheses mismatch, helps catch downstream syntax errors
            file_path, ext = os.path.splitext(code_suggestion.file_path)
            if ext.removeprefix(".") in ["java", "c", "cpp", "h", "hpp", "js", "ts", "jsx", "tsx", "go", "rs"]:
                for parentheses in ["()", "{}", "[]"]:
                    left, right = parentheses
                    old_parentheses_diff = original_code.count(left) - original_code.count(right)
                    new_parentheses_diff = new_code.count(left) - new_code.count(right)
                    if old_parentheses_diff != new_parentheses_diff:
                        # check for smallest surrounding span with corrected parentheses
                        best_superspan = ""
                        if new_parentheses_diff == 0:
                            best_superspan = find_smallest_valid_superspan(original_code, file_contents)
                            if best_superspan:
                                return f"You have a mismatch in parentheses in <original_code>. Your <original_code> has {original_code.count(left)} opening and {original_code.count(right)} closing parentheses:\n```\n{original_code}\n```\nYou can correct this by extending the code to the following:\n```\n{best_superspan}\n```"
                        if not best_superspan:
                            # use naive error message otherwise
                            error_message = ""
                            if old_parentheses_diff != 0:
                                error_message += f" Your <original_code> has {original_code.count(left)} opening and {original_code.count(right)} closing parentheses:\n```\n{original_code}\n```\n"
                            if new_parentheses_diff != 0:
                                error_message += f" Your <new_code> has {new_code.count(left)} opening and {new_code.count(right)} closing parentheses:\n```\n{new_code}\n```\n"
                            return error_message + "Make sure the number of opening and closing parentheses match in both <original_code> and <new_code>, otherwise the changes will cause a syntax error."

def sort_and_fuse_snippets(
    snippets: list[Snippet],
    fuse_distance: int = 600,
) -> list[Snippet]:
    if len(snippets) <= 1:
        return snippets
    new_snippets = []
    snippets.sort(key=lambda x: x.start)
    current_snippet = snippets[0]
    for snippet in snippets[1:]:
        if current_snippet.end + fuse_distance >= snippet.start:
            current_snippet.end = max(current_snippet.end, snippet.end)
            current_snippet.score = max(current_snippet.score, snippet.score)
        else:
            new_snippets.append(current_snippet)
            current_snippet = snippet
    new_snippets.append(current_snippet)
    return new_snippets
    
def organize_snippets(snippets: list[Snippet], fuse_distance: int=600) -> list[Snippet]:
    """
    Fuse and dedup snippets that are contiguous. Combine ones of same file.
    """
    fused_snippets = []
    added_file_paths = set()
    for i, snippet in enumerate(snippets):
        if snippet.file_path in added_file_paths:
            continue
        added_file_paths.add(snippet.file_path)
        current_snippets = [snippet]
        for current_snippet in snippets[i + 1:]:
            if snippet.file_path == current_snippet.file_path:
                current_snippets.append(current_snippet)
        current_snippets = sort_and_fuse_snippets(current_snippets, fuse_distance=fuse_distance)
        fused_snippets.extend(current_snippets)
    return fused_snippets

def get_max_snippets(
    snippets: list[Snippet],
    budget: int = SNIPPET_TOKEN_BUDGET,
    expand: int = 300,
):
    """
    Start with max number of snippets and then remove then until the budget is met.
    Return the resulting organized snippets.
    """
    if not snippets:
        return []
    START_INDEX = min(len(snippets), MAX_SNIPPETS)
    for i in range(START_INDEX, 0, -1):
        expanded_snippets = [snippet.expand(expand * 2) if snippet.type_name == "source" else snippet for snippet in snippets[:i]]
        proposed_snippets = organize_snippets(expanded_snippets[:i])
        cost = sum([len(snippet.get_snippet(False, False)) for snippet in proposed_snippets])
        if cost <= budget:
            return proposed_snippets
    raise Exception("Budget number of chars too low!")

def partition_snippets_if_test(snippets: list[Snippet], include_tests=False):
    if include_tests:
        return [snippet for snippet in snippets if "test" in snippet.file_path]
    return [snippet for snippet in snippets if "test" not in snippet.file_path]

def format_snippets(
    relevant_snippets: list[Snippet],
    read_only_snippets: list[Snippet],
    problem_statement: str,
):
    relevant_snippet_template = '<relevant_file index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</relevant_file>'
    formatted_relevant_snippets = []
    for i, snippet in enumerate(tqdm(relevant_snippets + read_only_snippets)):
        annotated_source_code, code_summaries = get_annotated_source_code(
            source_code=snippet.get_snippet(add_lines=False),
            issue_text=problem_statement,
            file_path=snippet.file_path,
        )
        formatted_relevant_snippets.append(
            relevant_snippet_template.format(
                i=i,
                file_path=snippet.file_path,
                content=annotated_source_code,
            )
        )
    joined_relevant_snippets = "\n".join(
        formatted_relevant_snippets
    )
    relevant_snippets_message = f"# Relevant codebase files:\nHere are the relevant files from the codebase. We previously summarized each of the files to help you solve the GitHub issue. These will be your primary reference to solve the problem:\n\n<relevant_files>\n{joined_relevant_snippets}\n</relevant_files>"
    return relevant_snippets_message

@streamable
def get_files_to_change(
    relevant_snippets: list[Snippet],
    read_only_snippets: list[Snippet],
    problem_statement: str,
    repo_name: str,
    cloned_repo: ClonedRepo,
    additional_context: str = "",
    import_graph: Graph | None = None,
    pr_diffs: str = "",
    chat_logger: ChatLogger = None,
    seed: int = 0,
    images: list[tuple[str, str, str]] | None = None
) -> Iterator[tuple[dict[str, str], list[FileChangeRequest], str]]:
    use_openai = False
    problem_statement = problem_statement.strip("\n")
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    user_facing_message = ""
    messages.append(
        Message(role="system", content=issue_sub_request_system_prompt, key="system")
    )

    new_relevant_snippets = []
    new_read_only_snippets = []
    
    for snippet in relevant_snippets:
        if snippet in new_relevant_snippets or snippet in new_read_only_snippets:
            continue
        if "test" in snippet.file_path:
            new_read_only_snippets.append(snippet)
        else:
            new_relevant_snippets.append(snippet)
    
    relevant_snippets = new_relevant_snippets
    read_only_snippets = new_read_only_snippets + read_only_snippets

    interleaved_snippets = []
    for i in range(max(len(relevant_snippets), len(read_only_snippets))):
        if i < len(relevant_snippets):
            interleaved_snippets.append(relevant_snippets[i])
        if i < len(read_only_snippets):
            interleaved_snippets.append(read_only_snippets[i])

    interleaved_snippets = partition_snippets_if_test(interleaved_snippets, include_tests=False)
    max_snippets = get_max_snippets(interleaved_snippets)
    relevant_snippets = [snippet for snippet in max_snippets if any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]
    read_only_snippets = [snippet for snippet in max_snippets if not any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]

    messages.append(
        Message(
            role="user",
            content=format_snippets(
                relevant_snippets,
                read_only_snippets,
                problem_statement,
            ),
            key="relevant_snippets",
        )
    )
    if additional_context:
        messages.append(
            Message(
                role="user",
                content=additional_context,
            )
        )
    messages.append(
        Message(
            role="user",
            content=f"# GitHub Issue\n<issue>\n{problem_statement}\n</issue>",
        )
    )
    if pr_diffs:
        messages.append(
            Message(role="user", content=pr_diffs, key="pr_diffs")
        )
    print("messages")
    for message in messages:
        print(message.content + "\n\n")
    joint_message = "\n\n".join(message.content for message in messages[1:])
    print("messages", joint_message)
    issue_sub_request_chat_gpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=issue_sub_request_system_prompt,
            ),
        ],
    )
    renames_chat_gpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=proposed_plan_system_prompt,
            ),
        ],
    )
    MODEL = "claude-3-opus-20240229"

    renames_response = renames_chat_gpt.chat_anthropic(
        content=joint_message + "\n\n" + anthropic_rename_prompt,
        temperature=0.1,
        images=images,
        use_openai=use_openai,
        seed=seed + 1,
        stop_sequences=["</renames>"],
        model=MODEL # haiku can troll this reponse
    )
    renames_dict = parse_renames(renames_response)
    # need better validation
    if renames_dict:
        relevant_snippets = [Snippet(
            file_path=renames_dict.get(snippet.file_path, snippet.file_path),
            start=snippet.start,
            end=snippet.end,
            content=snippet.content,
            score=snippet.score,
            type_name=snippet.type_name,
        ) for snippet in relevant_snippets]
        read_only_snippets = [Snippet(
            file_path=renames_dict.get(snippet.file_path, snippet.file_path),
            start=snippet.start,
            end=snippet.end,
            content=snippet.content,
            score=snippet.score,
            type_name=snippet.type_name,
        ) for snippet in read_only_snippets]
        messages = [
            message if message.key != "relevant_snippets" else Message(
                role="user",
                content=format_snippets(
                    relevant_snippets,
                    read_only_snippets,
                    problem_statement,
                ),
                key="relevant_snippets",
            ) for message in messages
        ]
        renames_string = "# Warning\n<warnings>\nIMPORTANT:" + "\n".join(
            f"`{old_name}` has already been renamed to `{new_name}`" for old_name, new_name in renames_dict.items()
        ) + "\nDo NOT include any renaming steps in your plan.\n</warnings>"
        messages.append(
            Message(
                role="user",
                content=renames_string,
                key="renames"
            )
        )
        joint_message = "\n\n".join(message.content for message in messages[1:])
        user_facing_message += "We decided to make the following renames to help you solve the GitHub issue:\n"  +"\n".join(
            f"Rename `{old_name}` to `{new_name}`" for old_name, new_name in renames_dict.items()
        ) + "\n\n"
        yield renames_dict, user_facing_message, []

    issue_sub_requests = ""
    if not use_openai:
        issue_sub_request_response = continuous_llm_calls(
            issue_sub_request_chat_gpt,
            content=joint_message + "\n\n" + issue_sub_request_prompt,
            model=MODEL,
            temperature=0.1,
            images=images,
            use_openai=use_openai,
            seed=seed,
            stop_sequences=["</issue_sub_requests>"],
            response_cleanup=cleanup_fcrs,
            MAX_CALLS=10
        )
        issue_sub_request_pattern = re.compile(r"<issue_sub_requests>(.*?)</issue_sub_requests>", re.DOTALL)
        issue_sub_request_match = issue_sub_request_pattern.search(issue_sub_request_response)
        if not issue_sub_request_match:
            raise Exception("Failed to match issue excerpts")
        issue_sub_requests = issue_sub_request_match.group(1)
        issue_sub_requests = issue_sub_requests.strip("\n")
        issue_sub_requests = re.sub(r"<justification>\n(.*?)\n</justification>\n*", "\n", issue_sub_requests, flags=re.DOTALL).strip("\n")

        user_facing_message += "I'm going to follow the following steps to help you solve the GitHub issue:\n" 
        single_issue_sub_request_pattern = re.compile(r"<issue_sub_request>(.*?)</issue_sub_request>", re.DOTALL)
        for i, single_issue_sub_request_match in enumerate(single_issue_sub_request_pattern.finditer(issue_sub_requests)):
            user_facing_message += f"{i + 1}. {single_issue_sub_request_match.group(1).strip()}\n"
        user_facing_message += "\n\n"
        yield renames_dict, user_facing_message, []

    open("msg.txt", "w").write(joint_message + "\n\n" + proposed_plan_prompt.format(issue_sub_requests=issue_sub_requests))
    
    chat_gpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=proposed_plan_system_prompt,
            ),
        ],
    )
    # handle stop sequences better for multiple chained calls
    proposed_plan_response: str = continuous_llm_calls(
        chat_gpt,
        content=joint_message + "\n\n" + proposed_plan_prompt.format(issue_sub_requests=issue_sub_requests),
        model=MODEL,
        temperature=0.1,
        images=images,
        use_openai=use_openai,
        seed=seed,
        stop_sequences=["</issue_analysis>"],
        response_cleanup=cleanup_fcrs,
        MAX_CALLS=10
    )
    # get the issue analysis from the proposed plan response
    issue_analysis_and_proposed_changes, failed , _ = extract_object_fields_from_string(proposed_plan_response, ["issue_analysis"])

    # TODO: add error case for no issue_analysis

    chat_gpt.messages= [
        Message(
            role="system",
            content=plan_generation_steps_system_prompt,
        ),
    ]
    # handle stop sequences better for multiple chained calls
    files_to_change_response: str = continuous_llm_calls(
        chat_gpt,
        content=joint_message + "\n\n" + plan_generation_steps_prompt.format(
            issue_analysis_and_proposed_changes=issue_analysis_and_proposed_changes
        ),
        model=MODEL,
        temperature=0.1,
        images=images,
        use_openai=use_openai,
        seed=seed,
        stop_sequences=["</plan>"],
        response_cleanup=cleanup_fcrs,
        MAX_CALLS=10
    )
    relevant_modules = []
    pattern = re.compile(r"<relevant_modules>(.*?)</relevant_modules>", re.DOTALL)
    relevant_modules_match = pattern.search(files_to_change_response)
    if relevant_modules_match:
        relevant_modules = [relevant_module.strip() for relevant_module in relevant_modules_match.group(1).split("\n") if relevant_module.strip()]
    file_change_requests = []
    try:
        for re_match in re.finditer(
            FileChangeRequest._regex, files_to_change_response, re.DOTALL
        ):
            file_change_request = FileChangeRequest.from_string(re_match.group(0))
            file_change_request.raw_relevant_files = " ".join(relevant_modules)
            file_change_request.filename = renames_dict.get(file_change_request.filename, file_change_request.filename)
            file_change_requests.append(file_change_request)
        
        yield renames_dict, user_facing_message + "Here are the changes we decided to make. I'm currently just making some edits:\n", file_change_requests
        error_message, error_indices = get_error_message(
            file_change_requests,
            cloned_repo,
            renames_dict=renames_dict,
        )
        # breakpoint()

        for error_resolution_count in range(3):
            if not error_message:
                break
            # todo: segment these into smaller calls to handle different edge cases
            # delete the error messages
            chat_gpt.messages = [message if message.role != "system" else Message(
                content=fix_files_to_change_system_prompt,
                role="system"
            ) for message in chat_gpt.messages]
            fix_attempt = continuous_llm_calls(
                chat_gpt,
                content=fix_files_to_change_prompt.format(
                    error_message=error_message,
                    allowed_indices=english_join([str(index) for index in range(len(error_indices))]),
                ),
                model=MODEL,
                temperature=0.1,
                images=images,
                seed=seed,
                stop_sequences=["</error_resolutions"],
                response_cleanup=cleanup_fcrs,
                use_openai=error_resolution_count < 2,
            )
            drops, matches = parse_patch_fcrs(fix_attempt)
            for index, new_fcr in matches:
                if index >= len(error_indices):
                    logger.warning(f"Index {index} not in error indices")
                    continue
                if "COPIED_FROM_PREVIOUS_MODIFY" in new_fcr.instructions:
                    # if COPIED_FROM_PREVIOUS_CREATE, we just need to override the filename
                    file_change_requests[error_indices[index]].filename = renames_dict.get(new_fcr.filename, new_fcr.filename)
                    continue
                file_change_requests[error_indices[index]] = new_fcr
            for drop in sorted(drops, reverse=True):
                if drop >= len(error_indices):
                    logger.warning(f"Index {drop} not in error indices")
                    continue
                file_change_requests.pop(error_indices[drop])
            logger.debug("Old indices", error_indices)
            error_message, error_indices = get_error_message(file_change_requests, cloned_repo, renames_dict=renames_dict)
            logger.debug("New indices", error_indices)
            yield renames_dict, user_facing_message + "Here are the changes we decided to make. I'm currently just making some edits:\n", file_change_requests

        set_fcr_change_type(file_change_requests, cloned_repo, renames_dict=renames_dict)
        yield renames_dict, user_facing_message + "Here are the changes we decided to make. I'm done making edits and now I'm just validating the changes using a linter to catch any mistakes like syntax errors or undefined variables:\n", file_change_requests
        return renames_dict, file_change_requests, files_to_change_response
    except RegexMatchError as e:
        print("RegexMatchError", e)

    return [], ""

@streamable
def get_files_to_change_for_on_comment(
    relevant_snippets: list[Snippet],
    read_only_snippets: list[Snippet],
    problem_statement: str,
    repo_name: str,
    cloned_repo: ClonedRepo,
    additional_context: str = "",
    import_graph: Graph | None = None,
    pr_info: str = "",
    pr_diffs: str = "",
    chat_logger: ChatLogger = None,
    seed: int = 0,
    images: list[tuple[str, str, str]] | None = None
) -> Iterator[tuple[dict[str, str], list[FileChangeRequest], str]]:
    use_openai = False
    problem_statement = problem_statement.strip("\n")
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    user_facing_message = ""
    messages.append(
        Message(role="system", content=issue_sub_request_on_comment_system_prompt, key="system")
    )

    new_relevant_snippets = []
    new_read_only_snippets = []
    
    for snippet in relevant_snippets:
        if snippet in new_relevant_snippets or snippet in new_read_only_snippets:
            continue
        if "test" in snippet.file_path:
            new_read_only_snippets.append(snippet)
        else:
            new_relevant_snippets.append(snippet)
    
    relevant_snippets = new_relevant_snippets
    read_only_snippets = new_read_only_snippets + read_only_snippets

    interleaved_snippets = []
    for i in range(max(len(relevant_snippets), len(read_only_snippets))):
        if i < len(relevant_snippets):
            interleaved_snippets.append(relevant_snippets[i])
        if i < len(read_only_snippets):
            interleaved_snippets.append(read_only_snippets[i])

    interleaved_snippets = partition_snippets_if_test(interleaved_snippets, include_tests=False)
    max_snippets = get_max_snippets(interleaved_snippets)
    relevant_snippets = [snippet for snippet in max_snippets if any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]
    read_only_snippets = [snippet for snippet in max_snippets if not any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]

    messages.append(
        Message(
            role="user",
            content=format_snippets(
                relevant_snippets,
                read_only_snippets,
                problem_statement,
            ),
            key="relevant_snippets",
        )
    )
    if additional_context:
        messages.append(
            Message(
                role="user",
                content=additional_context,
            )
        )
    if pr_info:
        messages.append(
            Message(
                role="user",
                content=f"# Pr Description - use this to get an idea of what the original pull request was about:\n\n{pr_info}",
            )
        )
    messages.append(
        Message(
            role="user",
            content=f"# Comment left on the Pull Request - THIS IS THE USER REQUEST YOU ARE TO RESOLVE:\n<user_comment>\n{problem_statement}\n</user_comment>",
        )
    )
    formatted_pr_diffs = on_comment_pr_diffs_format.format(pr_changes=pr_diffs)
    messages.append(
        Message(role="user", content=formatted_pr_diffs, key="pr_diffs")
    )
    print("messages")
    for message in messages:
        print(message.content + "\n\n")
    joint_message = "\n\n".join(message.content for message in messages[1:])
    print("messages", joint_message)
    issue_sub_request_chat_gpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=issue_sub_request_on_comment_system_prompt,
            ),
        ],
    )
    renames_chat_gpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=rename_on_comment_system_prompt,
            ),
        ],
    )
    MODEL = "claude-3-opus-20240229"

    renames_response = renames_chat_gpt.chat_anthropic(
        content=joint_message + "\n\n" + rename_on_comment_prompt,
        temperature=0.1,
        images=images,
        use_openai=use_openai,
        seed=seed + 1,
        stop_sequences=["</renames>"],
        model=MODEL # haiku can troll this reponse
    )
    renames_dict = parse_renames(renames_response)
    # need better validation
    if renames_dict:
        relevant_snippets = [Snippet(
            file_path=renames_dict.get(snippet.file_path, snippet.file_path),
            start=snippet.start,
            end=snippet.end,
            content=snippet.content,
            score=snippet.score,
            type_name=snippet.type_name,
        ) for snippet in relevant_snippets]
        read_only_snippets = [Snippet(
            file_path=renames_dict.get(snippet.file_path, snippet.file_path),
            start=snippet.start,
            end=snippet.end,
            content=snippet.content,
            score=snippet.score,
            type_name=snippet.type_name,
        ) for snippet in read_only_snippets]
        messages = [
            message if message.key != "relevant_snippets" else Message(
                role="user",
                content=format_snippets(
                    relevant_snippets,
                    read_only_snippets,
                    problem_statement,
                ),
                key="relevant_snippets",
            ) for message in messages
        ]
        renames_string = "# Warning\n<warnings>\nIMPORTANT:" + "\n".join(
            f"`{old_name}` has already been renamed to `{new_name}`" for old_name, new_name in renames_dict.items()
        ) + "\nDo NOT include any renaming steps in your plan.\n</warnings>"
        messages.append(
            Message(
                role="user",
                content=renames_string,
                key="renames"
            )
        )
        joint_message = "\n\n".join(message.content for message in messages[1:])
        user_facing_message += "We decided to make the following renames to help you solve the GitHub issue:\n"  +"\n".join(
            f"Rename `{old_name}` to `{new_name}`" for old_name, new_name in renames_dict.items()
        ) + "\n\n"
        yield renames_dict, user_facing_message, []

    issue_sub_requests = ""
    if not use_openai:
        issue_sub_request_response = continuous_llm_calls(
            issue_sub_request_chat_gpt,
            content=joint_message + "\n\n" + issue_sub_request_on_comment_prompt,
            model=MODEL,
            temperature=0.1,
            images=images,
            use_openai=use_openai,
            seed=seed,
            stop_sequences=["</issue_sub_requests>"],
            response_cleanup=cleanup_fcrs,
            MAX_CALLS=10
        )
        issue_sub_request_pattern = re.compile(r"<issue_sub_requests>(.*?)</issue_sub_requests>", re.DOTALL)
        issue_sub_request_match = issue_sub_request_pattern.search(issue_sub_request_response)
        if not issue_sub_request_match:
            raise Exception("Failed to match issue excerpts")
        issue_sub_requests = issue_sub_request_match.group(1)
        issue_sub_requests = issue_sub_requests.strip("\n")
        issue_sub_requests = re.sub(r"<justification>\n(.*?)\n</justification>\n*", "\n", issue_sub_requests, flags=re.DOTALL).strip("\n")

        user_facing_message += "I'm going to follow the following steps to help you solve the GitHub issue:\n" 
        single_issue_sub_request_pattern = re.compile(r"<issue_sub_request>(.*?)</issue_sub_request>", re.DOTALL)
        for i, single_issue_sub_request_match in enumerate(single_issue_sub_request_pattern.finditer(issue_sub_requests)):
            user_facing_message += f"{i + 1}. {single_issue_sub_request_match.group(1).strip()}\n"
        user_facing_message += "\n\n"
        yield renames_dict, user_facing_message, []

    open("msg.txt", "w").write(joint_message + "\n\n" + proposed_plan_on_comment_prompt.format(issue_sub_requests=issue_sub_requests))
    
    chat_gpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=proposed_plan_on_comment_system_prompt,
            ),
        ],
    )
    # handle stop sequences better for multiple chained calls
    proposed_plan_response: str = continuous_llm_calls(
        chat_gpt,
        content=joint_message + "\n\n" + proposed_plan_on_comment_prompt.format(issue_sub_requests=issue_sub_requests),
        model=MODEL,
        temperature=0.1,
        images=images,
        use_openai=use_openai,
        seed=seed,
        stop_sequences=["</issue_analysis>"],
        response_cleanup=cleanup_fcrs,
        MAX_CALLS=10
    )
    # get the issue analysis from the proposed plan response
    issue_analysis_and_proposed_changes, failed , _ = extract_object_fields_from_string(proposed_plan_response, ["issue_analysis"])

    # TODO: add error case for no issue_analysis

    chat_gpt.messages= [
        Message(
            role="system",
            content=plan_generation_steps_on_comment_system_prompt,
        ),
    ]
    # handle stop sequences better for multiple chained calls
    files_to_change_response: str = continuous_llm_calls(
        chat_gpt,
        content=joint_message + "\n\n" + plan_generation_steps_on_comment_prompt.format(
            issue_analysis_and_proposed_changes=issue_analysis_and_proposed_changes
        ),
        model=MODEL,
        temperature=0.1,
        images=images,
        use_openai=use_openai,
        seed=seed,
        stop_sequences=["</plan>"],
        response_cleanup=cleanup_fcrs,
        MAX_CALLS=10
    )
    relevant_modules = []
    pattern = re.compile(r"<relevant_modules>(.*?)</relevant_modules>", re.DOTALL)
    relevant_modules_match = pattern.search(files_to_change_response)
    if relevant_modules_match:
        relevant_modules = [relevant_module.strip() for relevant_module in relevant_modules_match.group(1).split("\n") if relevant_module.strip()]
    print("relevant_modules", relevant_modules)
    file_change_requests = []
    try:
        for re_match in re.finditer(
            FileChangeRequest._regex, files_to_change_response, re.DOTALL
        ):
            file_change_request = FileChangeRequest.from_string(re_match.group(0))
            file_change_request.raw_relevant_files = " ".join(relevant_modules)
            file_change_request.filename = renames_dict.get(file_change_request.filename, file_change_request.filename)
            file_change_requests.append(file_change_request)
        
        yield renames_dict, user_facing_message + "Here are the changes we decided to make. I'm currently just making some edits:\n", file_change_requests
        
        error_message, error_indices = get_error_message(
            file_change_requests,
            cloned_repo,
            renames_dict=renames_dict,
        )

        for error_resolution_count in range(3):
            if not error_message:
                break
            # todo: segment these into smaller calls to handle different edge cases
            # delete the error messages
            chat_gpt.messages = [message if message.role != "system" else Message(
                content=fix_files_to_change_system_prompt,
                role="system"
            ) for message in chat_gpt.messages]
            fix_attempt = continuous_llm_calls(
                chat_gpt,
                content=fix_files_to_change_prompt.format(
                    error_message=error_message,
                    allowed_indices=english_join([str(index) for index in range(len(error_indices))]),
                ),
                model=MODEL,
                temperature=0.1,
                images=images,
                seed=seed,
                stop_sequences=["</error_resolutions"],
                response_cleanup=cleanup_fcrs,
                use_openai=error_resolution_count < 2,
            )
            drops, matches = parse_patch_fcrs(fix_attempt)
            for index, new_fcr in matches:
                if index >= len(error_indices):
                    logger.warning(f"Index {index} not in error indices")
                    continue
                if "COPIED_FROM_PREVIOUS_MODIFY" in new_fcr.instructions:
                    # if COPIED_FROM_PREVIOUS_CREATE, we just need to override the filename
                    file_change_requests[error_indices[index]].filename = renames_dict.get(new_fcr.filename, new_fcr.filename)
                    continue
                file_change_requests[error_indices[index]] = new_fcr
            for drop in sorted(drops, reverse=True):
                if drop >= len(error_indices):
                    logger.warning(f"Index {drop} not in error indices")
                    continue
                file_change_requests.pop(error_indices[drop])
            logger.debug("Old indices", error_indices)
            error_message, error_indices = get_error_message(file_change_requests, cloned_repo, renames_dict=renames_dict)
            logger.debug("New indices", error_indices)
            yield renames_dict, user_facing_message + "Here are the changes we decided to make. I'm currently just making some edits:\n", file_change_requests

        set_fcr_change_type(file_change_requests, cloned_repo, renames_dict=renames_dict)
        yield renames_dict, user_facing_message + "Here are the changes we decided to make. I'm done making edits and now I'm just validating the changes using a linter to catch any mistakes like syntax errors or undefined variables:\n", file_change_requests
        return renames_dict, file_change_requests, files_to_change_response
    except RegexMatchError as e:
        print("RegexMatchError", e)

    return [], ""


def context_get_files_to_change(
    relevant_snippets: list[Snippet],
    read_only_snippets: list[Snippet],
    problem_statement,
    repo_name,
    cloned_repo: ClonedRepo,
    import_graph: Graph | None = None,
    pr_diffs: str = "",
    chat_logger: ChatLogger = None,
    seed: int = 0,
    images: list[tuple[str, str, str]] | None = None
):
    use_openai = True
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=issue_sub_request_system_prompt, key="system")
    )

    interleaved_snippets = []
    for i in range(max(len(relevant_snippets), len(read_only_snippets))):
        if i < len(relevant_snippets):
            interleaved_snippets.append(relevant_snippets[i])
        if i < len(read_only_snippets):
            interleaved_snippets.append(read_only_snippets[i])

    interleaved_snippets = partition_snippets_if_test(interleaved_snippets, include_tests=False)
    max_snippets = get_max_snippets(interleaved_snippets)
    if True:
        max_snippets = max_snippets[::-1]
    relevant_snippets = [snippet for snippet in max_snippets if any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]
    read_only_snippets = [snippet for snippet in max_snippets if not any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]

    relevant_snippet_template = '<relevant_file index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</relevant_file>'
    read_only_snippet_template = '<read_only_snippet index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</read_only_snippet>'
    # attach all relevant snippets
    joined_relevant_snippets = "\n".join(
        relevant_snippet_template.format(
            i=i,
            file_path=snippet.file_path,
            content=snippet.expand(300).get_snippet(add_lines=False) if snippet.type_name == "source" else snippet.get_snippet(add_lines=False),
        ) for i, snippet in enumerate(relevant_snippets)
    )
    relevant_snippets_message = f"# Relevant codebase files:\nHere are the relevant files from the codebase. These will be your primary reference to solve the problem:\n\n<relevant_files>\n{joined_relevant_snippets}\n</relevant_files>"
    messages.append(
        Message(
            role="user",
            content=relevant_snippets_message,
            key="relevant_snippets",
        )
    )
    joined_relevant_read_only_snippets = "\n".join(
        read_only_snippet_template.format(
            i=i,
            file_path=snippet.file_path,
            content=snippet.get_snippet(add_lines=False),
        ) for i, snippet in enumerate(read_only_snippets)
    )
    read_only_snippets_message = f"<relevant_read_only_snippets>\n{joined_relevant_read_only_snippets}\n</relevant_read_only_snippets>"
    if read_only_snippets:
        messages.append(
            Message(
                role="user",
                content=read_only_snippets_message,
                key="relevant_snippets",
            )
        )
    if import_graph:
        graph_string = ""
        reverse_graph = import_graph.reverse()
        for snippet in relevant_snippets + read_only_snippets:
            file_path = snippet.file_path
            if file_path not in reverse_graph or not reverse_graph[file_path]:
                continue
            graph_string += f"\nThe file '{file_path}' is imported by the following files:\n"
            for import_path in reverse_graph[file_path]:
                if ".venv" in import_path or "build" in import_path:
                    continue
                graph_string += f"- {import_path}\n"
            graph_string = graph_string.strip('\n')
        messages.append(
            Message(
                role="user",
                content=f"# Here's the structure of the imports:\n<import_graph>\n{graph_string}\n</import_graph>",
            )
        )
    messages.append(
        Message(
            role="user",
            content=f"# GitHub Issue\n<issue>\n{problem_statement}\n</issue>",
        )
    )
    if pr_diffs:
        messages.append(
            Message(role="user", content=pr_diffs, key="pr_diffs")
        )

    print("messages")
    for message in messages:
        print(message.content + "\n\n")
    joint_message = "\n\n".join(message.content for message in messages[1:])
    print("messages", joint_message)

    chat_gpt = ChatGPT(
        messages=[
            Message(
                role="system",
                content=context_files_to_change_system_prompt,
            ),
        ],
    )
    MODEL = "claude-3-opus-20240229"
    open("msg.txt", "w").write(joint_message + "\n\n" + context_files_to_change_prompt)
    files_to_change_response = chat_gpt.chat_anthropic(
        content=joint_message + "\n\n" + context_files_to_change_prompt,
        model=MODEL,
        temperature=0.1,
        images=images,
        use_openai=use_openai,
    )
    relevant_files = []
    read_only_files = []
    # parse out <relevant_files> block
    relevant_files_pattern = re.compile(r"<relevant_files>(.*?)</relevant_files>", re.DOTALL)
    relevant_files_matches = relevant_files_pattern.findall(files_to_change_response)
    if relevant_files_matches:
        relevant_files_str = '\n'.join(relevant_files_matches)
        relevant_files = parse_filenames(relevant_files_str)
    # parse out <read_only_files> block
    read_only_files_pattern = re.compile(r"<read_only_files>(.*?)</read_only_files>", re.DOTALL)
    read_only_files_matches = read_only_files_pattern.findall(files_to_change_response)
    if read_only_files_matches:
        read_only_files_str = '\n'.join(read_only_files_matches)
        read_only_files = parse_filenames(read_only_files_str)
    relevant_files = list(dict.fromkeys(relevant_files))
    read_only_files = list(dict.fromkeys(read_only_files))
    return relevant_files, read_only_files

def get_files_to_change_for_test(
    relevant_snippets: list[Snippet],
    read_only_snippets: list[Snippet],
    problem_statement: str,
    updated_files: dict[str, dict[str, str]],
    cloned_repo: ClonedRepo,
    import_graph: Graph | None = None,
    chat_logger: ChatLogger = None,
) -> tuple[list[FileChangeRequest], str]:
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=issue_sub_request_system_prompt, key="system")
    )

    # keep order but move all files without tests to read only snippets
    new_relevant_snippets = []
    new_read_only_snippets = []
    for snippet in relevant_snippets + read_only_snippets:
        if snippet in new_relevant_snippets or snippet in new_read_only_snippets:
            continue
        if "test" in snippet.file_path:
            new_relevant_snippets.append(snippet)
        else:
            new_read_only_snippets.append(snippet)
    
    relevant_snippets = new_relevant_snippets
    read_only_snippets = new_read_only_snippets

    for relevant_snippet in relevant_snippets:
        if relevant_snippet.file_path in updated_files:
            relevant_snippet.content = updated_files[relevant_snippet.file_path]["contents"]
    
    for read_only_snippet in read_only_snippets:
        if read_only_snippet.file_path in updated_files:
            read_only_snippet.content = updated_files[read_only_snippet.file_path]["contents"]


    interleaved_snippets = []
    for i in range(max(len(relevant_snippets), len(read_only_snippets))):
        if i < len(relevant_snippets):
            interleaved_snippets.append(relevant_snippets[i])
        if i < len(read_only_snippets):
            interleaved_snippets.append(read_only_snippets[i])
    
    max_snippets = get_max_snippets(interleaved_snippets)
    max_snippets = max_snippets[::-1]
    relevant_snippets = [snippet for snippet in max_snippets if any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]
    read_only_snippets = [snippet for snippet in max_snippets if not any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]

    relevant_snippet_template = '<relevant_file index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</relevant_file>'
    read_only_snippet_template = '<read_only_snippet index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</read_only_snippet>'
    # attach all relevant snippets
    if read_only_snippets:
        joined_relevant_read_only_snippets = "\n".join(
            read_only_snippet_template.format(
                i=i,
                file_path=snippet.file_path,
                content=snippet.get_snippet(add_lines=False),
            ) for i, snippet in enumerate(read_only_snippets)
        )
        read_only_snippets_message = f"<relevant_read_only_snippets>\n{joined_relevant_read_only_snippets}\n</relevant_read_only_snippets>"
        messages.append(
            Message(
                role="user",
                content=read_only_snippets_message,
                key="relevant_snippets",
            )
        )
    if True:
        formatted_relevant_snippets = []
        for i, snippet in enumerate(tqdm(relevant_snippets)):
            annotated_source_code, code_summaries = get_annotated_source_code(
                source_code=snippet.get_snippet(add_lines=False),
                issue_text=problem_statement,
                file_path=snippet.file_path,
            )
            formatted_relevant_snippets.append(
                relevant_snippet_template.format(
                    i=i,
                    file_path=snippet.file_path,
                    content=annotated_source_code,
                )
            )
        joined_relevant_snippets = "\n".join(
            formatted_relevant_snippets
        )
    else:
        joined_relevant_snippets = "\n".join(
            relevant_snippet_template.format(
                i=i,
                file_path=snippet.file_path,
                content=snippet.expand(300).get_snippet(add_lines=False),
            ) for i, snippet in enumerate(relevant_snippets)
        )
    relevant_snippets_message = f"# Relevant codebase files:\nHere are the relevant files from the codebase. We previously summarized each of the files to help you solve the GitHub issue. These will be your primary reference to solve the problem:\n\n<relevant_files>\n{joined_relevant_snippets}\n</relevant_files>"
    messages.append(
        Message(
            role="user",
            content=relevant_snippets_message,
            key="relevant_snippets",
        )
    )
    messages.append(
        Message(
            role="user",
            content=f"# GitHub Issue\n<issue>\n{problem_statement}\n</issue>",
        )
    )
    diff_string = ""
    for file_path, file_info in updated_files.items():
        diff_string += f"```diff\n{file_path}\n{generate_diff(file_info['original_contents'], file_info['contents'], n=10)}\n```"
    if diff_string:
        messages.append(
            Message(
                role="user",
                content=f"# Here are the changes we have made to resolve the issue that needs testing:\n<diff>\n{diff_string}\n</diff>\n",
                key="pr_diffs"
            )
        )
    if import_graph:
        graph_string = ""
        reverse_graph = import_graph.reverse()
        for snippet in relevant_snippets + read_only_snippets:
            file_path = snippet.file_path
            if file_path not in reverse_graph or not reverse_graph[file_path]:
                continue
            graph_string += f"\nThe file '{file_path}' is imported by the following files:\n"
            for import_path in reverse_graph[file_path]:
                if ".venv" in import_path or "build" in import_path:
                    continue
                graph_string += f"- {import_path}\n"
        messages.append(
            Message(
                role="user",
                content=f"# Here's the structure of the imports:\n<import_graph>\n{graph_string}\n</import_graph>",
            )
        )
    try:
        print("messages")
        for message in messages:
            print(message.content + "\n\n")
        joint_message = "\n\n".join(message.content for message in messages[1:])
        print("messages", joint_message)
        chat_gpt = ChatGPT(
            messages=[
                Message(
                    role="system",
                    content=test_files_to_change_system_prompt,
                ),
            ],
        )
        MODEL = "claude-3-opus-20240229"
        files_to_change_response: str = chat_gpt.chat_anthropic(
            content=joint_message + "\n\n" + test_files_to_change_prompt,
            model=MODEL,
            temperature=0.1,
        )
        # breakpoint()
        max_tokens = 4096 * 3.5 * 0.9 # approx max tokens per response
        expected_plan_count = 1
        call_anthropic_second_time = len(files_to_change_response) > max_tokens and files_to_change_response.count("</plan>") < expected_plan_count
        if call_anthropic_second_time:
            # ask for a second response
            try:
                second_response = chat_gpt.chat_anthropic(
                    content="",
                    model=MODEL,
                    temperature=0.1,
                )
                # we can simply concatenate the responses
                files_to_change_response += second_response
            except Exception as e:
                logger.warning(f"Failed to get second response due to {e}")
        if chat_logger:
            chat_logger.add_chat(
                {
                    "model": MODEL,
                    "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                    "output": files_to_change_response,
                })
        print("files_to_change_response", files_to_change_response)
        relevant_modules = []
        pattern = re.compile(r"<relevant_modules>(.*?)</relevant_modules>", re.DOTALL)
        relevant_modules_match = pattern.search(files_to_change_response)
        if relevant_modules_match:
            relevant_modules = [relevant_module.strip() for relevant_module in relevant_modules_match.group(1).split("\n") if relevant_module.strip()]
        print("relevant_modules", relevant_modules)
        file_change_requests = []
        for re_match in re.finditer(
            FileChangeRequest._regex, files_to_change_response, re.DOTALL
        ):
            file_change_request = FileChangeRequest.from_string(re_match.group(0))
            file_change_request.raw_relevant_files = " ".join(relevant_modules)
            file_change_requests.append(file_change_request)
        return file_change_requests, files_to_change_response
    except RegexMatchError as e:
        print("RegexMatchError", e)

    return [], ""


def get_files_to_change_for_gha(
    relevant_snippets: list[Snippet],
    read_only_snippets: list[Snippet],
    problem_statement: str,
    updated_files: dict[str, dict[str, str]],
    cloned_repo: ClonedRepo,
    pr_diffs: str = "",
    chat_logger: ChatLogger = None,
    use_faster_model: bool = False,
    use_openai: bool = False,
) -> tuple[list[FileChangeRequest], str]:
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=issue_sub_request_system_prompt, key="system")
    )
    # update the state of the snippets to be current
    for relevant_snippet in relevant_snippets:
        if relevant_snippet.file_path in updated_files:
            relevant_snippet.content = updated_files[relevant_snippet.file_path]["contents"]
    
    for read_only_snippet in read_only_snippets:
        if read_only_snippet.file_path in updated_files:
            read_only_snippet.content = updated_files[read_only_snippet.file_path]["contents"]

    interleaved_snippets = []
    for i in range(max(len(relevant_snippets), len(read_only_snippets))):
        if i < len(relevant_snippets):
            interleaved_snippets.append(relevant_snippets[i])
        if i < len(read_only_snippets):
            interleaved_snippets.append(read_only_snippets[i])

    max_snippets = get_max_snippets(interleaved_snippets)
    relevant_snippets = [snippet for snippet in max_snippets if any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]
    read_only_snippets = [snippet for snippet in max_snippets if not any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]

    read_only_snippet_template = '<read_only_snippet index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</read_only_snippet>'
    joined_relevant_read_only_snippets = "\n".join(
        read_only_snippet_template.format(
            i=i,
            file_path=snippet.file_path,
            content=snippet.get_snippet(add_lines=False),
        ) for i, snippet in enumerate(read_only_snippets)
    )
    read_only_snippets_message = f"<relevant_read_only_snippets>\n{joined_relevant_read_only_snippets}\n</relevant_read_only_snippets>"
    if read_only_snippets:
        messages.append(
            Message(
                role="user",
                content=read_only_snippets_message,
                key="relevant_snippets",
            )
        )
    relevant_snippet_template = '<relevant_file index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</relevant_file>'
    joined_relevant_snippets = "\n".join(
        relevant_snippet_template.format(
            i=i,
            file_path=snippet.file_path,
            content=snippet.expand(300).get_snippet(add_lines=False) if snippet.type_name == "source" else snippet.get_snippet(add_lines=False),
        ) for i, snippet in enumerate(relevant_snippets)
    )
    relevant_snippets_message = f"# Relevant codebase files:\nHere are the relevant files from the codebase. These will be your primary reference to solve the problem:\n\n<relevant_files>\n{joined_relevant_snippets}\n</relevant_files>"
    messages.append(
        Message(
            role="user",
            content=relevant_snippets_message,
            key="relevant_snippets",
        )
    )
    messages.append(
        Message(
            role="user",
            content=f"# GitHub Issue\n<issue>\n{problem_statement}\n</issue>",
        )
    )
    if pr_diffs:
        messages.append(
            Message(role="user", content=pr_diffs, key="pr_diffs")
        )
    if use_faster_model:
        file_paths_in_context = "\n".join(
            snippet.file_path for snippet in relevant_snippets + read_only_snippets
        )
        messages.append(
            Message(
                role="user",
                content=f"Here are all the file paths in context:\n<file_paths_in_context>\n{file_paths_in_context}\n<file_paths_in_context>",
            )
        )
    try:
        print("messages")
        for message in messages:
            print(message.content + "\n\n")
        joint_message = "\n\n".join(message.content for message in messages[1:])
        print("messages", joint_message)
        chat_gpt = ChatGPT(
            messages=[
                Message(
                    role="system",
                    content=gha_files_to_change_system_prompt,
                ),
            ],
        )
        MODEL = "claude-3-opus-20240229" if not use_faster_model else "claude-3-sonnet-20240229"
        continuous_llm_calls(
            chat_gpt,
            content=joint_message + "\n\n" + gha_files_to_change_prompt,
            model=MODEL,
            temperature=0.1,
            stop_sequences=["</reflection>"],
            response_cleanup=cleanup_fcrs,
            MAX_CALLS=10,
            use_openai=use_openai,
        )
        chat_gpt.messages[-1].content += "</reflection>\n"
        chat_gpt.messages[0].content = gha_files_to_change_system_prompt_2
        files_to_change_response = continuous_llm_calls(
            chat_gpt,
            content=gha_files_to_change_prompt_2,
            model=MODEL,
            temperature=0.1,
            stop_sequences=["</plan>"],
            response_cleanup=cleanup_fcrs,
            MAX_CALLS=10,
            use_openai=False,
        ) + "\n</plan>"

        if chat_logger:
            chat_logger.add_chat(
                {
                    "model": MODEL,
                    "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                    "output": files_to_change_response,
                })
        print("files_to_change_response", files_to_change_response)
        relevant_modules = []
        pattern = re.compile(r"<relevant_modules>(.*?)</relevant_modules>", re.DOTALL)
        relevant_modules_match = pattern.search(files_to_change_response)
        if relevant_modules_match:
            relevant_modules = [relevant_module.strip() for relevant_module in relevant_modules_match.group(1).split("\n") if relevant_module.strip()]
        print("relevant_modules", relevant_modules)
        file_change_requests = []
        for re_match in re.finditer(
            FileChangeRequest._regex, files_to_change_response, re.DOTALL
        ):
            file_change_request = FileChangeRequest.from_string(re_match.group(0))
            file_change_request.raw_relevant_files = " ".join(relevant_modules)
            file_change_requests.append(file_change_request)

        error_message, error_indices = get_error_message(file_change_requests, cloned_repo, updated_files)

        for _ in range(3):
            if not error_message:
                break
            chat_gpt.messages = [message for message in chat_gpt.messages if message.key != "system"]
            fix_attempt = continuous_llm_calls(
                chat_gpt,
                content=fix_files_to_change_prompt.format(
                    error_message=error_message,
                    allowed_indices=english_join([str(index) for index in range(len(error_indices))]),
                ),
                model=MODEL,
                temperature=0.1,
                stop_sequences=["</error_resolutions"],
                response_cleanup=cleanup_fcrs,
                MAX_CALLS=10,
                use_openai=use_openai,
            )
            drops, matches = parse_patch_fcrs(fix_attempt)
            for index, new_fcr in matches:
                if index >= len(error_indices):
                    logger.warning(f"Index {index} not in error indices")
                    continue
                if new_fcr.change_type == "create" and "COPIED_FROM_PREVIOUS_CREATE" in new_fcr.instructions:
                    # if COPIED_FROM_PREVIOUS_CREATE, we just need to override the filename
                    file_change_requests[error_indices[index]].filename = new_fcr.filename
                    continue
                file_change_requests[error_indices[index]] = new_fcr

            for drop in sorted(drops, reverse=True):
                if drop >= len(error_indices):
                    logger.warning(f"Index {drop} not in error indices")
                    continue
                file_change_requests.pop(error_indices[drop])
            logger.debug("Old indices", error_indices)
            error_message, error_indices = get_error_message(file_change_requests, cloned_repo, updated_files)
            logger.debug("New indices", error_indices)

        # breakpoint()
        set_fcr_change_type(file_change_requests, cloned_repo)
        return file_change_requests, files_to_change_response
    except RegexMatchError as e:
        print("RegexMatchError", e)

    return [], ""
