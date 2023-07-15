import traceback

import openai
from loguru import logger

from sweepai.core.entities import NoFilesException, Snippet
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs_modified as get_pr_diffs
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
    # snippet
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
    # Check if the comment is "REVERT"
    if comment.strip().upper() == "REVERT":
        rollback_file(repo_full_name, pr_path, installation_id, pr_number)
        return {"success": True, "message": "File has been reverted to the previous commit."}

    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR
    logger.info(
        f"Calling on_comment() with the following arguments: {comment}, {repo_full_name}, {repo_description}, {pr_path}")
    organization, repo_name = repo_full_name.split("/")
    metadata = {
        "repo_full_name": repo_full_name,
        "repo_name": repo_name,
        "organization": organization,
        "repo_description": repo_description,
        "installation_id": installation_id,
        "username": username,
        "function": "on_comment",
        "mode": PREFIX,
    }

    posthog.capture(username, "started", properties=metadata)
    logger.info(f"Getting repo {repo_full_name}")
    file_comment = pr_path and pr_line_position
    try:
        g = get_github_client(installation_id)
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        try:
            if not comment_id:
                pass
            elif not file_comment:
