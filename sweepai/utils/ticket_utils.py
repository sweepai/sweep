from sweepai.config.client import SweepConfig
from sweepai.core.entities import Snippet
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.str_utils import total_number_of_snippet_tokens, num_of_snippets_to_query
import traceback
from time import time
from loguru import logger
from sweepai.utils.event_logger import posthog
from sweepai.utils.search_utils import search_snippets


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
