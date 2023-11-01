from sweepai.config.client import SweepConfig
from sweepai.core.entities import Snippet
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.str_utils import total_number_of_snippet_tokens, num_of_snippets_to_query, blockquote, ordinal
import traceback
from time import time
from loguru import logger
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from loguru import logger
from sweepai.utils.event_logger import posthog
from sweepai.utils.search_utils import search_snippets
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr


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

SLOW_MODE = False
SLOW_MODE = True


def post_process_snippets(
    snippets: list[Snippet],
    max_num_of_snippets: int = 5,
    exclude_snippets: list[str] = [],
):
    snippets = [
        snippet
        for snippet in snippets
        if not any(
            snippet.file_path.endswith(ext) for ext in SweepConfig().exclude_exts
        )
    ]
    snippets = [
        snippet
        for snippet in snippets
        if not any(
            snippet.file_path.startswith(exclude_snippet)
            for exclude_snippet in exclude_snippets
        )
    ]

    snippets = snippets[: min(len(snippets), max_num_of_snippets * 10)]
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


def log_error(
    is_paying_user,
    is_trial_user,
    username,
    issue_url,
    error_type,
    exception,
    priority=0,
):
    if is_paying_user or is_trial_user:
        if priority == 1:
            priority = 0
        elif priority == 2:
            priority = 1

    prefix = ""
    if is_trial_user:
        prefix = " (TRIAL)"
    if is_paying_user:
        prefix = " (PRO)"

    content = (
        f"**{error_type} Error**{prefix}\n{username}:"
        f" {issue_url}\n```{exception}```"
    )
    discord_log_error(content, priority=priority)


def center(text: str) -> str:
    return f"<div align='center'>{text}</div>"
