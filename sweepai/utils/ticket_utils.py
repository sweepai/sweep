import traceback
from time import time

from loguru import logger

from sweepai.config.client import SweepConfig, get_blocked_dirs
from sweepai.core.context_pruning import RepoContextManager, get_relevant_context
from sweepai.core.lexical_search import (
    compute_vector_search_scores,
    prepare_lexical_search_index,
    search_index,
)
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import TicketProgress


@file_cache()
def get_top_k_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    ticket_progress: TicketProgress | None = None,
    k: int = 7,
):
    sweep_config: SweepConfig = SweepConfig()
    blocked_dirs = get_blocked_dirs(cloned_repo.repo)
    sweep_config.exclude_dirs += blocked_dirs
    _, snippets, lexical_index = prepare_lexical_search_index(
        cloned_repo.cached_dir,
        sweep_config,
        ticket_progress,
        ref_name=f"{str(cloned_repo.git_repo.head.commit.hexsha)}",
    )
    if ticket_progress:
        ticket_progress.search_progress.indexing_progress = (
            ticket_progress.search_progress.indexing_total
        )
        ticket_progress.save()

    for snippet in snippets:
        snippet.file_path = snippet.file_path[len(cloned_repo.cached_dir) + 1 :]
    content_to_lexical_score = search_index(query, lexical_index)
    files_to_scores = compute_vector_search_scores(query, snippets)
    for snippet in snippets:
        vector_score = files_to_scores.get(snippet.denotation, 0.04)
        snippet_score = 0.02
        if snippet.denotation in content_to_lexical_score:
            # roughly fine tuned vector score weight based on average score from search_eval.py on 10 test cases Feb. 13, 2024
            snippet_score = content_to_lexical_score[snippet.denotation] + (
                vector_score * 3.5
            )
            content_to_lexical_score[snippet.denotation] = snippet_score
        else:
            content_to_lexical_score[snippet.denotation] = snippet_score * vector_score

    ranked_snippets = sorted(
        snippets,
        key=lambda snippet: content_to_lexical_score[snippet.denotation],
        reverse=True,
    )
    ranked_snippets = ranked_snippets[:k]
    return ranked_snippets, snippets, content_to_lexical_score


def prep_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    ticket_progress: TicketProgress | None = None,
    k: int = 7,
):
    ranked_snippets, snippets, content_to_lexical_score = get_top_k_snippets(
        cloned_repo, query, ticket_progress, k
    )
    if ticket_progress:
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
    _, dir_obj = cloned_repo.list_directory_tree(
        included_directories=prefixes,
        included_files=snippet_paths,
    )
    repo_context_manager = RepoContextManager(
        dir_obj=dir_obj,
        current_top_tree=str(dir_obj),
        current_top_snippets=ranked_snippets,
        snippets=snippets,
        snippet_scores=content_to_lexical_score,
        cloned_repo=cloned_repo,
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
    is_paying_user,
    is_consumer_tier,
    issue_url,
    chat_logger,
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
            formatted_query,
            repo_context_manager,
            ticket_progress,
            chat_logger=chat_logger,
        )
        snippets = repo_context_manager.current_top_snippets
        ticket_progress.search_progress.repo_tree = str(repo_context_manager.dir_obj)
        ticket_progress.search_progress.final_snippets = snippets
        ticket_progress.save()

        tree = str(repo_context_manager.dir_obj)
        dir_obj = repo_context_manager.dir_obj
    except Exception as e:
        trace = traceback.format_exc()
        logger.exception(f"{trace} (tracking ID: `{tracking_id}`)")
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
    discord_log_error(content, priority=2)


def center(text: str) -> str:
    return f"<div align='center'>{text}</div>"


def fire_and_forget_wrapper(call):
    """
    This decorator is used to run a function in a separate thread.
    It does not return anything and does not wait for the function to finish.
    It fails silently.
    """

    def wrapper(*args, **kwargs):
        try:
            return call(*args, **kwargs)
        except Exception:
            pass
        # def run_in_thread(call, *a, **kw):
        #     try:
        #         call(*a, **kw)
        #     except:
        #         pass

        # thread = Thread(target=run_in_thread, args=(call,) + args, kwargs=kwargs)
        # thread.start()

    return wrapper
