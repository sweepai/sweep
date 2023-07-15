import traceback

import openai
from loguru import logger

from sweepai.core.entities import NoFilesException, Snippet
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.config.server import PREFIX, OPENAI_API_KEY, GITHUB_BOT_TOKEN
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import (
    get_github_client,
    search_snippets,
)
from sweepai.utils.prompt_constructor import HumanMessageCommentPrompt

github_access_token = GITHUB_BOT_TOKEN
openai.api_key = OPENAI_API_KEY

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2
num_extended_snippets = 2


def post_process_snippets(snippets: list[Snippet], max_num_of_snippets: int = 3):
    for snippet in snippets[:num_full_files]:
        snippet = snippet.expand()

    # snippet fusing
    i = 0
    while i < len(snippets):
        j = i + 1
        while j < len(snippets):
            if snippets[i] ^ snippets[j]:  # this checks for overlap
                snippets[i] = snippets[i] | snippets[j]  # merging
                snippets.pop(j)
            else:
                j += 1
        i += 1

    # truncating snippets based on character length
    result_snippets = []
    total_length = 0
    for snippet in snippets:
        total_length += len(snippet.get_snippet())
        if total_length > total_number_of_snippet_tokens * 5:
            break
        result_snippets.append(snippet)
    return result_snippets[:max_num_of_snippets]


def on_comment(
        repo_full_name: str,
        repo_description: str,
        comment: str,
        pr_path: str | None,
        pr_line_position: int | None,
        username: str,
        installation_id: int,
        pr_number: int = None,
        comment_id: int | None = None,
):
    ...
    diffs = get_pr_diffs(repo, pr)
    ...
    human_message = HumanMessageCommentPrompt(
        comment=comment,
        repo_name=repo_name,
        repo_description=repo_description if repo_description else "",
        diffs=f"<file_diffs path={pr_file_path}>{diffs}</file_diffs>",
        issue_url=pr.html_url,
        username=username,
        title=pr_title,
        tree=tree,
        summary=pr_body,
        snippets=snippets,
        pr_file_path=pr_file_path,  # may be None
        pr_line=pr_line,  # may be None
    )
    ...


def rollback_file(repo_full_name, pr_path, installation_id, pr_number):
    g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    branch_name = pr.head.ref

    # Get the file's content from the previous commit
    commits = repo.get_commits(sha=branch_name)
    if commits.totalCount < 2:
        current_file = repo.get_contents(pr_path, ref=commits[0].sha)
        current_file_sha = current_file.sha
        previous_content = repo.get_contents(pr_path, ref=repo.default_branch)
        previous_file_content = previous_content.decoded_content.decode("utf-8")
        repo.update_file(pr_path, "Revert file to previous commit", previous_file_content, current_file_sha,
                         branch=branch_name)
        return
    previous_commit = commits[1]

    # Get current file SHA
    current_file = repo.get_contents(pr_path, ref=commits[0].sha)
    current_file_sha = current_file.sha

    # Check if the file exists in the previous commit
    try:
        previous_content = repo.get_contents(pr_path, ref=previous_commit.sha)
        previous_file_content = previous_content.decoded_content.decode("utf-8")
        # Create a new commit with the previous file content
        repo.update_file(pr_path, "Revert file to previous commit", previous_file_content, current_file_sha,
                         branch=branch_name)
    except Exception as e:
        logger.error(traceback.format_exc())
        if e.status == 404:
            logger.warning(f"File {pr_path} was not found in previous commit {previous_commit.sha}")
        else:
            raise e
