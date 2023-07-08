import os
import openai

from loguru import logger
import modal

from sweepai.core.entities import FileChangeRequest, PullRequest
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import review_pr
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client
from sweepai.utils.constants import DB_NAME, PREFIX

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

update_index = modal.Function.lookup(DB_NAME, "update_index")

num_of_snippets_to_query = 10
max_num_of_snippets = 5
def create_pr(
    file_change_requests: list[FileChangeRequest],
    pull_request: PullRequest,
    sweep_bot: SweepBot,
    username: str,
    installation_id: int,
    branch: str,
    issue_number: int | None = None
):
    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR

    organization, repo_name = sweep_bot.repo.full_name.split("/")
    metadata = {
        "repo_full_name": sweep_bot.repo.full_name,
        "organization": organization,
        "repo_name": repo_name,
        "repo_description": sweep_bot.repo.description,
        "username": username,
        "installation_id": installation_id,
        "function": "on_ticket",
        "mode": PREFIX,
    }
    posthog.capture(username, "started", properties=metadata)

    try:
        branch = sweep_bot.create_branch(branch)
        completed_count, fcr_count = sweep_bot.change_files_in_github(file_change_requests, branch)
        if completed_count == 0 and fcr_count != 0:
            logger.info("No changes made")
            posthog.capture(
                username,
                "failed",
                properties={
                    "error": "No changes made",
                    "reason": "No changes made",
                    **metadata,
                },
            )
            return {"success": False, "error": "No changes made"}

        # Include issue number in PR description
        if issue_number:
            pr_description = f"{pull_request.content}\n\nFixes #{issue_number}.\n\nTo checkout this PR branch, run the following command in your terminal:\n```zsh\ngit checkout {branch}\n```"
        else:
            pr_description = f"{pull_request.content}\n\nTo checkout this PR branch, run the following command in your terminal:\n```zsh\ngit checkout {branch}\n```"

        pr = sweep_bot.repo.create_pull(
            title=pull_request.title,
            body=pr_description,
            head=branch,
            base=sweep_bot.repo.default_branch,
        )
    except openai.error.InvalidRequestError as e:
        logger.error(e)
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Invalid request error / context length",
                **metadata,
            },
        )
        raise e
    except Exception as e:
        logger.error(e)
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Unexpected error",
                **metadata,
            },
        )
        raise e

    posthog.capture(username, "success", properties={**metadata})
    logger.info("create_pr success")
    return {"success": True, "pull_request": pr}

