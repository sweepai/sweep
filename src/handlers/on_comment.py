"""
On Github ticket, get ChatGPT to deal with it
"""

# TODO: Add file validation

import os
import openai

from loguru import logger

from src.core.sweep_bot import SweepBot
from src.handlers.on_review import get_pr_diffs
from src.utils.event_logger import posthog
from src.utils.github_utils import (
    get_github_client,
    search_snippets,
)
from src.utils.prompt_constructor import HumanMessageCommentPrompt
from src.utils.constants import PREFIX

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

def on_comment(
    repo_full_name: str,
    repo_description: str,
    comment: str,
    pr_path: str | None,
    pr_line_position: int | None,
    username: str,
    installation_id: int,
    pr_number: int = None,
):
    # Check if the comment is "REVERT"
    if comment.strip().upper() == "REVERT":
        rollback_file(repo_full_name, pr_path, installation_id, pr_number)
        return {"success": True}

    posthog.capture(username, "started", properties=metadata)
    logger.info(f"Getting repo {repo_full_name}")
    try:
        g = get_github_client(installation_id)
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        branch_name = pr.head.ref
        pr_title = pr.title
        pr_body = pr.body
        diffs = get_pr_diffs(repo, pr)
        snippets, tree = search_snippets(repo, comment, installation_id, branch=branch_name, num_files=1 if pr_path else 3)
        pr_line = None
        pr_file_path = None
        if pr_path and pr_line_position:
            pr_file = repo.get_contents(pr_path, ref=branch_name).decoded_content.decode("utf-8")
            pr_lines = pr_file.splitlines()
            pr_line = pr_lines[min(len(pr_lines), pr_line_position) - 1]
            pr_file_path = pr_path.strip()

def rollback_file(repo_full_name, pr_path, installation_id, pr_number):
    # Get the Github client
    g = get_github_client(installation_id)

    # Get the repo
    repo = g.get_repo(repo_full_name)

    # Get the file at the specified path
    file = repo.get_contents(pr_path)

    # Get the SHA of the previous commit of the file
    previous_commit_sha = repo.get_commits(path=file.path)[1].sha

    # Get the file at the previous commit
    previous_file = repo.get_git_blob(previous_commit_sha)

    # Replace the current file with the previous version
    repo.update_file(file.path, "Reverted file to previous version", previous_file.content, file.sha)