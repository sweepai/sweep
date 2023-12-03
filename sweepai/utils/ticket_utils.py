import traceback
from time import time

from loguru import logger

from sweepai.config.client import SweepConfig
from sweepai.core.context_pruning import RepoContextManager, get_relevant_context
from sweepai.core.entities import Snippet
from sweepai.core.lexical_search import search_index
from sweepai.core.vector_db import prepare_lexical_search_index
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import TicketProgress
from sweepai.utils.str_utils import total_number_of_snippet_tokens
from sweepai.agents.query_filter_bot import QueryFilterBot


@file_cache()
def prep_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    ticket_progress: TicketProgress,
):
    sweep_config: SweepConfig = SweepConfig()

    file_list, snippets, lexical_index = prepare_lexical_search_index(
        cloned_repo, sweep_config, cloned_repo.repo_full_name, ticket_progress
    )
    ticket_progress.search_progress.indexing_progress = (
        ticket_progress.search_progress.indexing_total
    )
    ticket_progress.save()

    for snippet in snippets:
        snippet.file_path = snippet.file_path[len(cloned_repo.cached_dir) + 1 :]

        query_filter_bot = QueryFilterBot()
    try:
        processed_query = query_filter_bot.filter_query(query)
    except Exception as filter_error:
        raise Exception(f"Query filtering failed: {filter_error}") from filter_error
    content_to_lexical_score = search_index(processed_query, lexical_index)
    snippet_to_key = (
        lambda snippet: f"{snippet.file_path}:{snippet.start}:{snippet.end}"
    )

    snippet_scores = []
    for snippet in snippets:
        snippet_score = 0.1
        if snippet_to_key(snippet) in content_to_lexical_score:
            snippet_score = content_to_lexical_score[snippet_to_key(snippet)]
        snippet_scores.append(snippet_score)
    ranked_snippets = sorted(
        snippets,
        key=lambda snippet: snippet_scores[snippets.index(snippet)],
        reverse=True,
    )
    ranked_snippets = ranked_snippets[:7]
    ticket_progress.search_progress.retrieved_snippets = ranked_snippets
    ticket_progress.save()
    snippet_paths = [snippet.file_path for snippet in ranked_snippets]
    prefixes = []
    for snippet_path in snippet_paths:
        snippet_depth = len(snippet_path.split("/"))
        for idx in range(snippet_depth):  # heuristic
            if idx > snippet_depth // 2:
                prefixes.append("/".join(snippet_path.split("/")[:idx]) + "/")
        prefixes.append(snippet_path)
    included_files = [snippet.file_path for snippet in ranked_snippets]
    _, dir_obj = cloned_repo.list_directory_tree(
        included_directories=prefixes,
        included_files=included_files,
    )
    repo_context_manager = RepoContextManager(
        dir_obj=dir_obj,
        current_top_tree=str(dir_obj),
        current_top_snippets=ranked_snippets,
        snippets=snippets,
        snippet_scores=content_to_lexical_score,
    )
    return repo_context_manager


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
    ticket_progress: TicketProgress,
):
    logger.info("Fetching relevant files...")
    try:
        search_query = (title + summary + replies_text).strip("\n")
        replies_text = f"\n{replies_text}" if replies_text else ""
        formatted_query = (f"{title.strip()}\n{summary.strip()}" + replies_text).strip(
            "\n"
        )
        repo_context_manager = prep_snippets(cloned_repo, search_query, ticket_progress)
        ticket_progress.search_progress.repo_tree = str(repo_context_manager.dir_obj)
        ticket_progress.save()

        repo_context_manager = get_relevant_context(
            formatted_query, repo_context_manager, ticket_progress
        )
        snippets = repo_context_manager.current_top_snippets
        ticket_progress.search_progress.repo_tree = str(repo_context_manager.dir_obj)
        ticket_progress.search_progress.final_snippets = snippets
        ticket_progress.save()

        tree = str(repo_context_manager.dir_obj)
        dir_obj = repo_context_manager.dir_obj
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
