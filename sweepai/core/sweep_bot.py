import base64
import re
import traceback
from typing import Dict

from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from loguru import logger
from networkx import Graph
from pydantic import BaseModel
from tqdm import tqdm
from rapidfuzz import fuzz

from sweepai.agents.modify_utils import contains_ignoring_whitespace, english_join, find_best_match, find_best_matches, find_max_indentation, parse_fcr, indent
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DEFAULT_GPT4_MODEL
from sweepai.core.annotate_code_openai import get_annotated_source_code
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import (
    FileChangeRequest,
    Message,
    NoFilesException,
    ProposedIssue,
    PullRequest,
    RegexMatchError,
    Snippet,
)
from sweepai.core.prompts import (
    context_files_to_change_prompt,
    context_files_to_change_system_prompt,
    pull_request_prompt,
    subissues_prompt,
    gha_files_to_change_system_prompt,
    gha_files_to_change_prompt,
    test_files_to_change_system_prompt,
    test_files_to_change_prompt,
    fix_files_to_change_prompt
)
from sweepai.core.planning_prompts import (
    files_to_change_system_prompt,
    files_to_change_prompt,
    issue_excerpt_prompt,
    issue_excerpt_system_prompt,
)
from sweepai.utils.chat_logger import ChatLogger
# from sweepai.utils.previous_diff_utils import get_relevant_commits
from sweepai.utils.diff import generate_diff
from sweepai.utils.progress import (
    TicketProgress,
)
from sweepai.utils.str_utils import get_hash
from sweepai.utils.github_utils import ClonedRepo

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"
SNIPPET_TOKEN_BUDGET = 150_000 * 3.5  # 140k tokens
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

You have previously already made the following changes:
<changes_made>
{changes_made}
</changes_made>

Fix the above GitHub Actions."""

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

def safe_decode(
    repo: Repository,
    path: str,
    *args,
    **kwargs
):
    """
    By default, this function will decode the file contents from the repo.
    But if the file > 1MB, we will fetch the raw content and then decode it manually ourselves.
    It's a strange bug that occurs when the file is too large and the GitHub API doesn't decode it properly and returns encoding="none".
    Reference: https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28#get-repository-content
    """
    try:
        contents = repo.get_contents(path, *args, **kwargs)
        if contents.encoding == "none":
            blob = repo.get_git_blob(contents.sha)
            # this might be more correct but chatgpt said the latter is better
            # return base64.b64decode(bytearray(blob.content, "utf-8")).decode("utf-8")
            return base64.b64decode(blob.content).decode("utf-8")
        return contents.decoded_content.decode("utf-8")
    except GithubException as e:
        raise e
    except Exception as e:
        raise e

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
    # Regular expression pattern to match file names
    pattern = r'\b(?:[\w-]+/)*[\w-]+(?:[.:]\w+)+\b|\b(?:[\w-]+/)+[\w-]+\b'

    # Find all occurrences of file names in the text
    filenames = re.findall(pattern, text)
    return filenames

def is_blocked(file_path: str, blocked_dirs: list[str]):
    for blocked_dir in blocked_dirs:
        if file_path.startswith(blocked_dir) and len(blocked_dir) > 0:
            return {"success": True, "path": blocked_dir}
    return {"success": False}

def validate_file_change_requests(
    file_change_requests: list[FileChangeRequest],
    cloned_repo: ClonedRepo,
):
    # TODO: add better suffixing
    for fcr in file_change_requests:
        if fcr.change_type == "modify":
            try:
                cloned_repo.get_file_contents(fcr.filename)
            except FileNotFoundError as e:
                logger.warning(f"Failed to get file contents for {fcr.filename} due to {e}, trying prefixes")
                for file_path in cloned_repo.get_file_list():
                    if file_path.endswith(fcr.filename):
                        logger.info(f"Found similar file {fcr.filename} at {file_path}")
                        cloned_repo.get_file_contents(file_path)
                        fcr.filename = file_path
                        break
                else:
                    fcr.change_type = "create" # need better handling
        elif fcr.change_type == "create":
            try:
                cloned_repo.get_file_contents(fcr.filename)
                fcr.change_type = "modify" # need better handling
            except FileNotFoundError:
                pass

def get_error_message(
    file_change_requests: list[FileChangeRequest],
    cloned_repo: ClonedRepo,
    updated_files: dict[str, dict[str, str]] = {},
):
    def get_file_contents(file_path):
        if file_path in updated_files:
            return updated_files[file_path]["contents"]
        return cloned_repo.get_file_contents(file_path)
    error_message = ""
    error_indices = []
    for i, file_change_request in enumerate(file_change_requests):
        if file_change_request.change_type == "modify":
            try:
                file_contents = get_file_contents(file_change_request.filename)
                parsed_fcr = parse_fcr(file_change_request)
                if not parsed_fcr["original_code"]:
                    # breakpoint()
                    error_message += f"<error index=\"{len(error_indices)}\">\nYou forgot to provide both an <original_code> block. Here is what you provided in the instructions:\n```\n{file_change_request.instructions}\n```\nIf you would like to drop this task use the <drop> marker.\n</error>\n\n"
                    error_indices.append(i)
                    continue
                if not parsed_fcr["new_code"]:
                    error_message += f"<error index=\"{len(error_indices)}\">\nYou forgot to a <new_code> block. Here is what you provided in the instructions:\n```\n{file_change_request.instructions}\n```\nIf you would like to drop this task use the <drop> marker.\n</error>\n\n"
                    error_indices.append(i)
                    continue
                original_code = parsed_fcr["original_code"][0].strip("\n")
                if original_code == parsed_fcr["new_code"][0].strip("\n"):
                    error_message += f"<error index=\"{len(error_indices)}\">\n<original_code> and <new_code> are the same. You must provide a different code snippet in <new_code>.\n</error>\n\n"
                    error_indices.append(i)
                    continue
                if not original_code:
                    error_message += f"<error index=\"{len(error_indices)}\">\nThe <original_code> can not be empty. If you would like to append code, copy the code you want to append the new code after into the <original_code>, then copy the same code into <new_code>, then finally append the new code after <new_code>.\n</error>\n\n"
                    error_indices.append(i)
                else:
                    if not contains_ignoring_whitespace(original_code, file_contents):
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
                            error_message += f"<error index=\"{len(error_indices)}\">\n<original_code> does not exist in `{file_change_request.filename}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nBut the code is no where to be found in the file. There are also no similar code snippets in this file.{too_long_message}{ellipses_message}\n</error>\n\n"
                            continue

                        if best_score == 100:
                            continue
                        if best_score > 80:
                            error_message += f"<error index=\"{len(error_indices)}\">\n<original_code> does not exist in `{file_change_request.filename}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nDid you mean to modify the following code instead?\n```\n{best_match}\n```\nHere is the diff between your proposed <original_code> and the most similar code in the file:\n```diff\n{generate_diff(indent(original_code, best_indent), best_match, n=10)}\n```{too_long_message}{ellipses_message}\n</error>\n\n"
                        else:
                            best_matches = find_best_matches(original_code, file_contents, threshold=threshold, tokenized=True)
                            if len(best_matches) > 1:
                                best_matches_string = "\n\n".join([f"Code match {i}:\n```\n{match_}\n```" for i, (match_, score) in enumerate(best_matches)])
                                error_message += f"<error index=\"{len(error_indices)}\">\n<original_code> does not exist in `{file_change_request.filename}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nDid you mean to modify one of the following pieces of code instead?\n{best_matches_string}{too_long_message}{ellipses_message}\n</error>\n\n"
                            else:
                                # Same as case > 80
                                error_message += f"<error index=\"{len(error_indices)}\">\n<original_code> does not exist in `{file_change_request.filename}`. Your proposed <original_code> contains:\n```\n{indent(original_code, best_indent)}\n```\nDid you mean to modify the following code instead?\n```\n{best_match}\n```\nHere is the diff between your proposed <original_code> and the most similar code in the file:\n```diff\n{generate_diff(indent(original_code, best_indent), best_match, n=10)}\n```{too_long_message}{ellipses_message}\n</error>\n\n"
                        error_indices.append(i)
            except FileNotFoundError as e:
                logger.warning(f"Failed to get file contents for {file_change_request.filename} due to {e}")
                for file_path in cloned_repo.get_file_list():
                    if file_path.endswith(file_change_request.filename):
                        logger.info(f"Found similar file {file_change_request.filename} at {file_path}")
                        get_file_contents(file_path)
                        file_change_request.filename = file_path
                else:
                    error_message += f"<error index=\"{len(error_indices)}\">\nThe file `{file_change_request.filename}` does not exist. Double-check your spelling. Did you mean to create a file with <create>?\n</error>\n\n"
                    error_indices.append(i)
    # if error_message:
    #     breakpoint()
    return error_message.strip('\n\n'), error_indices
        
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
        expanded_snippets = [snippet.expand(expand * 2) for snippet in snippets[:i]]
        proposed_snippets = organize_snippets(expanded_snippets[:i])
        cost = sum([len(snippet.get_snippet(False, False)) for snippet in proposed_snippets])
        if cost <= budget:
            return proposed_snippets
    raise Exception("Budget number of chars too low!")

def partition_snippets_if_test(snippets: list[Snippet], include_tests=False):
    if include_tests:
        return [snippet for snippet in snippets if "test" in snippet.file_path]
    return [snippet for snippet in snippets if "test" not in snippet.file_path]

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
) -> tuple[list[FileChangeRequest], str]:
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=issue_excerpt_system_prompt, key="system")
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

    relevant_snippet_template = '<relevant_file index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</relevant_file>'
    # read_only_snippet_template = '<read_only_snippet index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</read_only_snippet>'
    # attach all relevant snippets
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
        # cohere_rerank_response = cohere_rerank_call(
        #     query=problem_statement,
        #     documents=code_summaries,
        # )
    joined_relevant_snippets = "\n".join(
        formatted_relevant_snippets
    )
    relevant_snippets_message = f"# Relevant codebase files:\nHere are the relevant files from the codebase. We previously summarized each of the files to help you solve the GitHub issue. These will be your primary reference to solve the problem:\n\n<relevant_files>\n{joined_relevant_snippets}\n</relevant_files>"
    messages.append(
        Message(
            role="user",
            content=relevant_snippets_message,
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
    try:
        print("messages")
        for message in messages:
            print(message.content + "\n\n")
        joint_message = "\n\n".join(message.content for message in messages[1:])
        print("messages", joint_message)
        issue_excerpt_chat_gpt = ChatGPT(
            messages=[
                Message(
                    role="system",
                    content=issue_excerpt_system_prompt,
                ),
            ],
        )
        chat_gpt = ChatGPT(
            messages=[
                Message(
                    role="system",
                    content=files_to_change_system_prompt,
                ),
            ],
        )
        ISSUE_EXCERPT_MODEL = "claude-3-haiku-20240307"
        MODEL = "claude-3-opus-20240229"
        issue_excerpt_response = issue_excerpt_chat_gpt.chat_anthropic(
            content=joint_message + "\n\n" + (issue_excerpt_prompt),
            model=ISSUE_EXCERPT_MODEL,
            temperature=0.1,
            images=images,
            use_openai=True,
            seed=seed
        )
        issue_excerpt_pattern = re.compile(r"<issue_excerpts>(.*?)</issue_excerpts>", re.DOTALL)
        issue_excerpt_match = issue_excerpt_pattern.search(issue_excerpt_response)
        if not issue_excerpt_match:
            raise Exception("Failed to match issue excerpts")
        issue_excerpts = issue_excerpt_match.group(1)
        issue_excerpts = issue_excerpts.strip("\n")
        files_to_change_response: str = chat_gpt.chat_anthropic(
            content=joint_message + "\n\n" + (files_to_change_prompt.format(issue_excerpts=issue_excerpts)),
            model=MODEL,
            temperature=0.1,
            # images=images,
            use_openai=True,
            seed=seed
        )
        expected_plan_count = 1
        calls = 0
        # pylint: disable=E1101
        while files_to_change_response.count("</plan>") < expected_plan_count and calls < 3:
            # ask for a second response
            try:
                next_response: str = chat_gpt.chat_anthropic(
                    content="Continue generating, making sure to finish the plan coherently. You may be in the middle of an XML block or section of code.",
                    model=MODEL,
                    temperature=0.1,
                    # images=images,
                    use_openai=True,
                    seed=seed
                )
                # we can simply concatenate the responses
                files_to_change_response += next_response
            except Exception as e:
                logger.warning(f"Failed to get second response due to {e}")
            calls += 1
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
        
        error_message, error_indices = get_error_message(file_change_requests, cloned_repo)
        # breakpoint()

        for _ in range(3):
            if not error_message:
                break
            fix_attempt = chat_gpt.chat_anthropic(
                content=fix_files_to_change_prompt.format(
                    error_message=error_message,
                    allowed_indices=english_join([str(index) for index in range(len(error_indices))]),
                ),
                model=MODEL,
                temperature=0.1,
                images=images,
                seed=seed,
                use_openai=True
            )
            drops, matches = parse_patch_fcrs(fix_attempt)
            for index, new_fcr in matches:
                if index >= len(error_indices):
                    logger.warning(f"Index {index} not in error indices")
                    continue
                file_change_requests[error_indices[index]] = new_fcr
            for drop in sorted(drops, reverse=True):
                if drop >= len(error_indices):
                    logger.warning(f"Index {drop} not in error indices")
                    continue
                file_change_requests.pop(error_indices[drop])
            logger.debug("Old indices", error_indices)
            error_message, error_indices = get_error_message(file_change_requests, cloned_repo)
            logger.debug("New indices", error_indices)
            # breakpoint()
        # breakpoint()

        validate_file_change_requests(file_change_requests, cloned_repo)
        return file_change_requests, files_to_change_response
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
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=issue_excerpt_system_prompt, key="system")
    )

    interleaved_snippets = []
    for i in range(max(len(relevant_snippets), len(read_only_snippets))):
        if i < len(relevant_snippets):
            interleaved_snippets.append(relevant_snippets[i])
        if i < len(read_only_snippets):
            interleaved_snippets.append(read_only_snippets[i])

    interleaved_snippets = partition_snippets_if_test(interleaved_snippets, include_tests=False)
    # we can change this to be a length + score penalty
    interleaved_snippets = [snippet for snippet in interleaved_snippets if snippet.score > RELEVANCE_THRESHOLD] # this will break if old caches exist
    max_snippets = get_max_snippets(interleaved_snippets)
    if True:
        max_snippets = max_snippets[::-1]
    relevant_snippets = [snippet for snippet in max_snippets if any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]
    read_only_snippets = [snippet for snippet in max_snippets if not any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]

    relevant_snippet_template = '<relevant_file index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</relevant_file>'
    read_only_snippet_template = '<read_only_snippet index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</read_only_snippet>'
    # attach all relevant snippets
    if False:
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
            # cohere_rerank_response = cohere_rerank_call(
            #     query=problem_statement,
            #     documents=code_summaries,
            # )
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
    # previous_diffs = get_previous_diffs(
    #     problem_statement,
    #     cloned_repo=cloned_repo,
    #     relevant_file_paths=[snippet.file_path for snippet in relevant_snippets],
    # )
    # messages.append( # temporarily disable in main
    #     Message(
    #         role="user",
    #         content=previous_diffs,
    #     )
    # )
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
                    content=context_files_to_change_system_prompt,
                ),
            ],
        )
        MODEL = "claude-3-opus-20240229"
        files_to_change_response = chat_gpt.chat_anthropic(
            content=joint_message + "\n\n" + (context_files_to_change_prompt),
            model=MODEL,
            temperature=0.1,
            use_openai=True,
            images=images
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
    except Exception as e:
        logger.info(f"Failed to get context due to {e}")
    return [], []

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
        Message(role="system", content=issue_excerpt_system_prompt, key="system")
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
            use_openai=True,
        )
        # breakpoint()
        max_tokens = 4096 * 3.5 * 0.9 # approx max tokens per response
        expected_plan_count = 1
        # pylint: disable=E1101
        call_anthropic_second_time = len(files_to_change_response) > max_tokens and files_to_change_response.count("</plan>") < expected_plan_count
        if call_anthropic_second_time:
            # ask for a second response
            try:
                second_response = chat_gpt.chat_anthropic(
                    content="",
                    model=MODEL,
                    temperature=0.1,
                    use_openai=True
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
) -> tuple[list[FileChangeRequest], str]:
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=issue_excerpt_system_prompt, key="system")
    )

    for relevant_snippet in relevant_snippets:
        if relevant_snippet.file_path in updated_files:
            relevant_snippet.content = updated_files[relevant_snippet.file_path]["contents"]
    
    for read_only_snippet in read_only_snippets:
        if read_only_snippet.file_path in updated_files:
            read_only_snippet.content = updated_files[read_only_snippet.file_path]["contents"]

    new_relevant_snippets = []
    new_read_only_snippets = []
    for snippet in relevant_snippets + read_only_snippets:
        if snippet in new_relevant_snippets or snippet in new_read_only_snippets:
            continue
        if "test" not in snippet.file_path:
            new_read_only_snippets.append(snippet)
        else:
            new_relevant_snippets.append(snippet)
    relevant_snippets = new_relevant_snippets
    read_only_snippets = new_read_only_snippets

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
    # previous_diffs = get_previous_diffs(
    #     problem_statement,
    #     cloned_repo=cloned_repo,
    #     relevant_file_paths=[snippet.file_path for snippet in relevant_snippets],
    # )
    # messages.append( # temporarily disable in main
    #     Message(
    #         role="user",
    #         content=previous_diffs,
    #     )
    # )
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
        files_to_change_response: str = chat_gpt.chat_anthropic(
            content=joint_message + "\n\n" + gha_files_to_change_prompt,
            model=MODEL,
            temperature=0.1,
            use_openai=True,
        )
        # breakpoint()
        max_tokens = 4096 * 3.5 * 0.8 # approx max tokens per response
        expected_plan_count = 1
        # pylint: disable=E1101
        call_anthropic_second_time = len(files_to_change_response) > max_tokens and files_to_change_response.count("</plan>") < expected_plan_count
        if call_anthropic_second_time:
            # ask for a second response
            try:
                second_response = chat_gpt.chat_anthropic(
                    content="",
                    model=MODEL,
                    temperature=0.1,
                    use_openai=True,
                )
                # we can simply concatenate the responses
                files_to_change_response += second_response
                chat_gpt.messages[-1].content += second_response
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

        error_message, error_indices = get_error_message(file_change_requests, cloned_repo, updated_files)

        for _ in range(3):
            if not error_message:
                break
            fix_attempt = chat_gpt.chat_anthropic(
                content=fix_files_to_change_prompt.format(
                    error_message=error_message,
                    allowed_indices=english_join([str(index) for index in range(len(error_indices))]),
                ),
                model=MODEL,
                # model="claude-3-opus-20240229",
                temperature=0.1,
            )
            drops, matches = parse_patch_fcrs(fix_attempt)
            for index, new_fcr in matches:
                if index >= len(error_indices):
                    logger.warning(f"Index {index} not in error indices")
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
        validate_file_change_requests(file_change_requests, cloned_repo)
        return file_change_requests, files_to_change_response
    except RegexMatchError as e:
        print("RegexMatchError", e)

    return [], ""

class CodeGenBot(ChatGPT):
    def generate_subissues(self, retries: int = 3):
        subissues: list[ProposedIssue] = []
        for count in range(retries):
            try:
                logger.info(f"Generating for the {count}th time...")
                files_to_change_response = self.chat(
                    subissues_prompt, message_key="subissues"
                )  # Dedup files to change here
                subissues = []
                for re_match in re.finditer(
                    ProposedIssue._regex, files_to_change_response, re.DOTALL
                ):
                    subissues.append(ProposedIssue.from_string(re_match.group(0)))
                if subissues:
                    return subissues
            except RegexMatchError:
                logger.warning("Failed to parse! Retrying...")
                self.delete_messages_from_chat("files_to_change")
                continue
        raise NoFilesException()

    def generate_pull_request(self, retries=2) -> PullRequest:
        for count in range(retries):
            try:
                pr_text_response = self.chat(
                    pull_request_prompt,
                    message_key="pull_request",
                    model=DEFAULT_GPT4_MODEL,
                )

                # Add triple quotes if not present
                if not pr_text_response.strip().endswith('"""'):
                    pr_text_response += '"""'

                self.messages = self.messages[:-2]
            except SystemExit:
                raise SystemExit
            except Exception as e:
                e_str = str(e)
                logger.warning(f"Exception {e_str}. Failed to parse! Retrying...")
                self.messages = self.messages[:-1]
                continue
            pull_request = PullRequest.from_string(pr_text_response)

            final_branch = pull_request.branch_name[:240]
            final_branch = final_branch.split("/", 1)[-1]

            use_underscores = get_branch_name_config(self.repo)
            if use_underscores:
                final_branch = final_branch.replace("/", "_")

            pull_request.branch_name = (
                "sweep/" if not use_underscores else "sweep_"
            ) + final_branch
            return pull_request
        raise Exception("Could not generate PR text")


class GithubBot(BaseModel):
    class Config:
        arbitrary_types_allowed = True  # for repo: Repository

    repo: Repository

    def get_contents(self, path: str, branch: str = ""):
        if not branch:
            branch = SweepConfig.get_branch(self.repo)
        try:
            return self.repo.get_contents(path, ref=branch)
        except Exception as e:
            logger.warning(path)
            raise e

    def get_file(self, file_path: str, branch: str = "") -> ContentFile:
        content = self.get_contents(file_path, branch)
        assert not isinstance(content, list)
        return content

    def check_path_exists(self, path: str, branch: str = ""):
        try:
            self.get_contents(path, branch)
            return True
        except SystemExit:
            raise SystemExit
        except Exception:
            return False

    def clean_branch_name(self, branch: str) -> str:
        branch = re.sub(r"[^a-zA-Z0-9_\-/]", "_", branch)
        branch = re.sub(r"_+", "_", branch)
        branch = branch.strip("_")

        return branch

    def create_branch(self, branch: str, base_branch: str = None, retry=True) -> str:
        # Generate PR if nothing is supplied maybe
        branch = self.clean_branch_name(branch)
        base_branch = self.repo.get_branch(
            base_branch if base_branch else SweepConfig.get_branch(self.repo)
        )
        try:
            try:
                test = self.repo.get_branch("sweep")
                assert test is not None
                # If it does exist, fix
                branch = branch.replace(
                    "/", "_"
                )  # Replace sweep/ with sweep_ (temp fix)
            except Exception:
                pass

            self.repo.create_git_ref(f"refs/heads/{branch}", base_branch.commit.sha)
            return branch
        except GithubException as e:
            logger.error(f"Error: {e}, trying with other branch names...")
            logger.warning(
                f"{branch}\n{base_branch}, {base_branch.name}\n{base_branch.commit.sha}"
            )
            if retry:
                for i in range(1, 10):
                    try:
                        logger.warning(f"Retrying {branch}_{i}...")
                        _hash = get_hash()[:5]
                        self.repo.create_git_ref(
                            f"refs/heads/{branch}_{_hash}", base_branch.commit.sha
                        )
                        return f"{branch}_{_hash}"
                    except GithubException:
                        pass
            else:
                new_branch = self.repo.get_branch(branch)
                if new_branch:
                    return new_branch.name
            logger.error(
                f"Error: {e}, could not create branch name {branch} on {self.repo.full_name}"
            )
            raise e

    def populate_snippets(self, snippets: list[Snippet]):
        for snippet in snippets:
            try:
                snippet.content = safe_decode(
                    self.repo,
                    snippet.file_path,
                    ref=SweepConfig.get_branch(self.repo)
                )
                snippet.start = max(1, snippet.start)
                snippet.end = min(len(snippet.content.split("\n")), snippet.end)
            except SystemExit:
                raise SystemExit
            except Exception:
                logger.error(snippet)

    def validate_file_change_requests(
        self, file_change_requests: list[FileChangeRequest], branch: str = ""
    ):
        blocked_dirs = get_blocked_dirs(self.repo)
        created_files = []
        for file_change_request in file_change_requests:
            try:
                contents = None
                try:
                    contents = self.repo.get_contents(
                        file_change_request.filename,
                        branch or SweepConfig.get_branch(self.repo),
                    )
                except UnknownObjectException:
                    for prefix in [
                        self.repo.full_name,
                        self.repo.owner.login,
                        self.repo.name,
                    ]:
                        try:
                            new_filename = file_change_request.filename.replace(
                                prefix + "/", "", 1
                            )
                            contents = self.repo.get_contents(
                                new_filename,
                                branch or SweepConfig.get_branch(self.repo),
                            )
                            file_change_request.filename = new_filename
                            break
                        except UnknownObjectException:
                            pass
                    else:
                        contents = None
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.error(f"FileChange Validation Error: {e}")

                if (
                    contents or file_change_request.filename in created_files
                ) and file_change_request.change_type == "create":
                    file_change_request.change_type = "modify"
                elif (
                    not (contents or file_change_request.filename in created_files)
                    and file_change_request.change_type == "modify"
                ):
                    file_change_request.change_type = "create"
                
                if contents is not None:
                    try:
                        file_change_request.old_content = safe_decode(self.repo, file_change_request.filename, ref=SweepConfig.get_branch(self.repo))
                    except Exception as e:
                        logger.info(f"Error: {e}")
                        file_change_request.old_content = ""

                created_files.append(file_change_request.filename)

                block_status = is_blocked(file_change_request.filename, blocked_dirs)
                if block_status["success"]:
                    # red X emoji
                    file_change_request.instructions = (
                        f'❌ Unable to modify files in `{block_status["path"]}`\nEdit'
                        " `sweep.yaml` to configure."
                    )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.info(traceback.format_exc())
                raise e
        file_change_requests = [
            file_change_request for file_change_request in file_change_requests
        ]
        return file_change_requests


ASSET_BRANCH_NAME = "sweep/assets"


class SweepBot(CodeGenBot, GithubBot):
    comment_pr_diff_str: str | None = None
    comment_pr_files_modified: Dict[str, str] | None = None
    ticket_progress: TicketProgress | None = None


    def validate_file_change_requests(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str = "",
    ):
        file_change_requests = super().validate_file_change_requests(
            file_change_requests, branch
        )
        return file_change_requests