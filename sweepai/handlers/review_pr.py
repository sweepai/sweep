import os
from time import sleep, time
import traceback
import backoff
from git import GitCommandError
from github.Repository import Repository
from github.PullRequest import PullRequest
from loguru import logger

from sweepai.chat.api import posthog_trace
from sweepai.core.review_utils import (
    format_pr_changes_by_file,
    get_pr_changes,
    get_pr_summary_from_patches,
    group_vote_review_pr,
    review_pr_detailed_checks,
)
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.ticket_rendering_utils import create_update_review_pr_comment
from sweepai.utils.ticket_utils import fire_and_forget_wrapper
from sweepai.utils.validate_license import validate_license
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog

@backoff.on_exception(
    backoff.expo,
    GitCommandError,
    max_tries=2,
)
@posthog_trace
def review_pr(
    username: str,
    pr: PullRequest,
    repository: Repository,
    installation_id: int,
    tracking_id: str | None = None,
    metadata: dict = {},
):
    if not os.environ.get("CLI"):
        assert (
            validate_license()
        ), "License key is invalid or expired. Please contact us at team@sweep.dev to upgrade to an enterprise license."
    with logger.contextualize(
        tracking_id=tracking_id,
    ):
        review_pr_start_time = time()
        chat_logger: ChatLogger = ChatLogger(
            {"username": username, "title": f"Review PR: {pr.number}"}
        )
        metadata = {
            "pr_url": pr.html_url,
            "repo_full_name": repository.full_name,
            "repo_description": repository.description,
            "username": username,
            "installation_id": installation_id,
            "function": "review_pr",
            "tracking_id": tracking_id,
        }

        try:
            # check if the pr has been merged or not
            if pr.state == "closed":
                fire_and_forget_wrapper(posthog.capture)(
                    username,
                    "pr_review pr_closed",
                    properties={
                        **metadata,
                        "duration": round(time() - review_pr_start_time),
                    },
                )
                return {"success": False, "reason": "PR is closed"}
            user_token, _ = get_github_client(installation_id)
            error: Exception = None

            try:
                sleep(15) # sleep for 15 seconds to prevent race conditions with github uploading remote branch
                cloned_repo: ClonedRepo = ClonedRepo(
                    repository.full_name,
                    installation_id=installation_id,
                    token=user_token,
                    repo=repository,
                    branch=pr.head.ref,
                )
            except GitCommandError as e:
                raise e
            except Exception as e:
                logger.error(f"Failure cloning repo in review_pr: {e}")
                error = Exception(
                    f"Failed to clone repository: {repository.full_name}. This may be because the branch `{pr.head.ref}` associated with this pull request no longer exists or Sweep does not have the necessary permissions to access your repository."
                )

            # try and update the user to let them know why we can not review the pr.
            # if the error is due to credential issues, this will probably not work
            if error:
                _comment_id = create_update_review_pr_comment(
                    username,
                    pr,
                    error_message=str(error),
                )
                return {"success": False, "reason": str(error)}

            # handle creating comments on the pr to tell the user we are going to begin reviewing the pr
            # _comment_id = create_update_review_pr_comment(username, pr)
            pr_changes, dropped_files, unsuitable_files = get_pr_changes(repository, pr)
            formatted_pr_changes_by_file = format_pr_changes_by_file(pr_changes)
            pull_request_summary = get_pr_summary_from_patches(
                pr_changes, chat_logger=chat_logger
            )
            # get initial code review by group vote
            code_review_by_file = group_vote_review_pr(
                username,
                pr_changes,
                formatted_pr_changes_by_file,
                multiprocess=True,
                chat_logger=chat_logger,
            )
            # do more specific checks now, i.e. duplicated util functions
            code_review_by_file = review_pr_detailed_checks(
                username,
                cloned_repo,
                pr_changes,
                code_review_by_file,
                chat_logger=chat_logger,
            )
            _comment_id = create_update_review_pr_comment(
                username,
                pr,
                code_review_by_file=code_review_by_file,
                pull_request_summary=pull_request_summary,
                dropped_files=dropped_files,
                unsuitable_files=unsuitable_files,
            )
        except Exception as e:
            posthog.capture(
                username,
                "review_pr failed",
                properties={
                    **metadata,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                    "duration": round(time() - review_pr_start_time),
                },
            )
            raise e
        logger.info("review_pr success in " + str(round(time() - review_pr_start_time)))
        return {"success": True}
