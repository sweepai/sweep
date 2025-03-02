import os
import openai
from loguru import logger
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import (
    get_github_client,
    search_snippets,
)
from sweepai.utils.prompt_constructor import HumanMessageCommentPrompt
from sweepai.utils.constants import PREFIX

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

def send_simple_response(repo, issue_number, message):
    """
    Send a simple response to a Github comment.
    """
    repo.get_issue(issue_number).create_comment(message)

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
    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR
    # 6. Send a simple response to the user
    # Rest of the code...
    send_simple_response(repo, pr_number, "Thank you for your comment. We are processing your request.")
    # Rest of the code...


