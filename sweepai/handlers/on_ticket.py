"""
on_ticket is the main function that is called when a new issue is created.
It is only called by the webhook handler in sweepai/api.py.
"""

import traceback
from time import time

import openai
from loguru import logger

from sweepai.config.server import OPENAI_API_KEY
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from sweepai.utils.event_logger import posthog
from sweepai.utils.search_utils import search_snippets
from sweepai.utils.str_utils import blockquote, num_of_snippets_to_query, ordinal
from sweepai.utils.ticket_utils import log_error

# from sandbox.sandbox_utils import Sandbox

openai.api_key = OPENAI_API_KEY

sweeping_gif = """<a href="https://github.com/sweepai/sweep"><img class="swing" src="https://raw.githubusercontent.com/sweepai/sweep/main/.assets/sweeping.gif" width="100" style="width:50px; margin-bottom:10px" alt="Sweeping"></a>"""


custom_config = """
extends: relaxed

rules:
    line-length: disable
    indentation: disable
"""


def review_code(
    repo,
    pr_changes,
    issue_url,
    username,
    repo_description,
    title,
    summary,
    replies_text,
    tree,
    lint_output,
    plan,
    chat_logger,
    commit_history,
    review_message,
    edit_sweep_comment,
    repo_full_name,
    installation_id,
):
    try:
        # CODE REVIEW
        changes_required, review_comment = review_pr(
            repo=repo,
            pr=pr_changes,
            issue_url=issue_url,
            username=username,
            repo_description=repo_description,
            title=title,
            summary=summary,
            replies_text=replies_text,
            tree=tree,
            lint_output=lint_output,
            plan=plan,  # plan for the PR
            chat_logger=chat_logger,
            commit_history=commit_history,
        )
        lint_output = None
        review_message += (
            f"Here is the {ordinal(1)} review\n" + blockquote(review_comment) + "\n\n"
        )
        if changes_required:
            edit_sweep_comment(
                review_message + "\n\nI'm currently addressing these suggestions.",
                3,
            )
            logger.info(f"Addressing review comment {review_comment}")
            on_comment(
                repo_full_name=repo_full_name,
                repo_description=repo_description,
                comment=review_comment,
                username=username,
                installation_id=installation_id,
                pr_path=None,
                pr_line_position=None,
                pr_number=None,
                pr=pr_changes,
                chat_logger=chat_logger,
                repo=repo,
            )
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
    return changes_required, review_message


def fetch_relevant_files(
    cloned_repo,
    title,
    summary,
    replies_text,
    username,
    metadata,
    on_ticket_start_time,
    tracking_id,
    edit_sweep_comment,
    is_paying_user,
    is_consumer_tier,
    issue_url,
):
    logger.info("Fetching relevant files...")
    try:
        snippets, tree, dir_obj = search_snippets(
            cloned_repo,
            f"{title}\n{summary}\n{replies_text}",
            num_files=num_of_snippets_to_query,
        )
        assert len(snippets) > 0
    except SystemExit:
        logger.warning("System exit")
        posthog.capture(
            username,
            "failed",
            properties={
                **metadata,
                "error": "System exit",
                "duration": time() - on_ticket_start_time,
            },
        )
        raise SystemExit
    except Exception as e:
        trace = traceback.format_exc()
        logger.exception(f"{trace} (tracking ID: `{tracking_id}`)")
        edit_sweep_comment(
            (
                "It looks like an issue has occurred around fetching the files."
                " Perhaps the repo has not been initialized. If this error persists"
                f" contact team@sweep.dev.\n\n> @{username}, editing this issue description to include more details will automatically make me relaunch. Please join our Discord server for support (tracking_id={tracking_id})"
            ),
            -1,
        )
        log_error(
            is_paying_user,
            is_consumer_tier,
            username,
            issue_url,
            "File Fetch",
            str(e) + "\n" + traceback.format_exc(),
            priority=1,
        )
        posthog.capture(
            username,
            "failed",
            properties={
                **metadata,
                "error": str(e),
                "duration": time() - on_ticket_start_time,
            },
        )
        raise e
    return snippets, tree, dir_obj
