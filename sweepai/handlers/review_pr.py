

import os
from time import time
import traceback
from github.Repository import Repository
from github.PullRequest import PullRequest
from loguru import logger


from sweepai.core.review_utils import PRReviewBot, format_pr_changes_by_file, get_pr_changes
from sweepai.utils.ticket_rendering_utils import create_update_review_pr_comment
from sweepai.utils.ticket_utils import fire_and_forget_wrapper
from sweepai.utils.validate_license import validate_license
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog


def review_pr(username: str, pr: PullRequest, repository: Repository, installation_id: int, tracking_id: str | None = None):
    if not os.environ.get("CLI"):
        assert validate_license(), "License key is invalid or expired. Please contact us at team@sweep.dev to upgrade to an enterprise license."
    with logger.contextualize(
        tracking_id=tracking_id,
    ):
        review_pr_start_time = time()
        chat_logger: ChatLogger = ChatLogger({"username": username,"title": f"Review PR: {pr.number}"})
        review_bot = PRReviewBot()
        posthog_metadata = {
            "pr_url": pr.html_url,
            "repo_full_name": repository.full_name,
            "repo_description": repository.description,
            "username": username,
            "installation_id": installation_id,
            "function": "review_pr",
            "tracking_id": tracking_id,
        }
        fire_and_forget_wrapper(posthog.capture)(
            username, "review_pr_started", properties=posthog_metadata
        )

        try:
            # check if the pr has been merged or not
            if pr.state == "closed":
                fire_and_forget_wrapper(posthog.capture)(
                    username,
                    "issue_closed",
                    properties={
                        **posthog_metadata,
                        "duration": round(time() - review_pr_start_time),
                    },
                )
                return {"success": False, "reason": "PR is closed"}
            # handle creating comments on the pr to tell the user we are going to begin reviewing the pr
            _comment_id = create_update_review_pr_comment(pr)
            pr_changes = get_pr_changes(repository, pr)
            logger.info(f"Fetched pr changes for {pr}.")
            formatted_pr_changes_by_file = format_pr_changes_by_file(pr_changes)
            code_review_by_file = review_bot.review_code_changes_by_file(formatted_pr_changes_by_file, chat_logger=chat_logger)
            _comment_id = create_update_review_pr_comment(pr, code_review_by_file=code_review_by_file)
        except Exception as e:
            posthog.capture(
                username,
                "review_pr_failed",
                properties={
                    **posthog_metadata,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                    "duration": round(time() - review_pr_start_time),
                },
            )
            raise e
        posthog.capture(
            username,
            "success",
            properties={**posthog_metadata, "duration": round(time() - review_pr_start_time)},
        )
        logger.info("review_pr success in " + str(round(time() - review_pr_start_time)))
        return {"success": True}