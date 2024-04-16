from collections import defaultdict
import traceback
from time import time

import cohere
from loguru import logger
from tqdm import tqdm
import networkx as nx

from sweepai.config.client import SweepConfig, get_blocked_dirs
from sweepai.config.server import COHERE_API_KEY
from sweepai.core.context_pruning import RepoContextManager, add_relevant_files_to_top_snippets, build_import_trees, integrate_graph_retrieval
from sweepai.core.entities import Snippet
from sweepai.core.lexical_search import (
    compute_vector_search_scores,
    prepare_lexical_search_index,
    search_index,
)
from sweepai.core.sweep_bot import get_files_to_change
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.multi_query import generate_multi_queries
from sweepai.utils.openai_listwise_reranker import listwise_rerank_snippets
from sweepai.utils.progress import TicketProgress

"""
Input queries are in natural language so both lexical search 
and vector search have a heavy bias towards natural language
files such as tests, docs and localization files. Therefore,
we add adjustment scores to compensate for this bias.
"""

prefix_adjustment = {
    ".": 0.5,
    "doc": 0.3,
    "example": 0.7,
}

suffix_adjustment = {
    ".cfg": 0.8,
    ".ini": 0.8,
    ".txt": 0.8,
    ".rst": 0.8,
    ".md": 0.8,
    ".html": 0.8,
    ".po": 0.5,
    ".json": 0.8,
    ".toml": 0.8,
    ".yaml": 0.8,
    ".yml": 0.8,
    ".1": 0.5, # man pages
    ".spec.ts": 0.6,
    ".spec.js": 0.6,
    ".generated.ts": 0.5,
    ".generated.graphql": 0.5,
    ".generated.js": 0.5,
    "ChangeLog": 0.5,
}

substring_adjustment = {
    "tests/": 0.5,
    "test_": 0.5,
    "_test": 0.5,
    "egg-info": 0.5,
    "LICENSE": 0.5,
}

def apply_adjustment_score(
    snippet: str,
    old_score: float,
):
    snippet_score = old_score
    file_path, *_ = snippet.split(":")
    file_path = file_path.lower()
    for prefix, adjustment in prefix_adjustment.items():
        if file_path.startswith(prefix):
            snippet_score *= adjustment
            break
    for suffix, adjustment in suffix_adjustment.items():
        if file_path.endswith(suffix):
            snippet_score *= adjustment
            break
    for substring, adjustment in substring_adjustment.items():
        if substring in file_path:
            snippet_score *= adjustment
            break
    # Penalize numbers as they are usually examples of:
    # 1. Test files (e.g. test_utils_3*.py)
    # 2. Generated files (from builds or snapshot tests)
    # 3. Versioned files (e.g. v1.2.3)
    # 4. Migration files (e.g. 2022_01_01_*.sql)
    base_file_name = file_path.split("/")[-1]
    num_numbers = sum(c.isdigit() for c in base_file_name)
    snippet_score *= (1 - 1 / len(base_file_name)) ** num_numbers
    return snippet_score

NUM_SNIPPETS_TO_RERANK = 100

@file_cache()
def multi_get_top_k_snippets(
    cloned_repo: ClonedRepo,
    queries: list[str],
    ticket_progress: TicketProgress | None = None,
    k: int = 15,
):
    """
    Handles multiple queries at once now. Makes the vector search faster.
    """
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
    # We can mget the lexical search scores for all queries at once
    # But it's not that slow anyways
    content_to_lexical_score_list = [search_index(query, lexical_index) for query in queries]
    files_to_scores_list = compute_vector_search_scores(queries, snippets)

    for i, query in enumerate(queries):
        for snippet in tqdm(snippets):
            vector_score = files_to_scores_list[i].get(snippet.denotation, 0.04)
            snippet_score = 0.02
            if snippet.denotation in content_to_lexical_score_list[i]:
                # roughly fine tuned vector score weight based on average score from search_eval.py on 10 test cases Feb. 13, 2024
                snippet_score = content_to_lexical_score_list[i][snippet.denotation] + (
                    vector_score * 3.5
                )
                content_to_lexical_score_list[i][snippet.denotation] = snippet_score
            else:
                content_to_lexical_score_list[i][snippet.denotation] = snippet_score * vector_score
            content_to_lexical_score_list[i][snippet.denotation] = apply_adjustment_score(
                snippet.denotation, content_to_lexical_score_list[i][snippet.denotation]
            )
    
    ranked_snippets_list = [
        sorted(
            snippets,
            key=lambda snippet: content_to_lexical_score[snippet.denotation],
            reverse=True,
        )[:k] for content_to_lexical_score in content_to_lexical_score_list
    ]
    return ranked_snippets_list, snippets, content_to_lexical_score_list

@file_cache()
def get_top_k_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    ticket_progress: TicketProgress | None = None,
    k: int = 15,
):
    ranked_snippets_list, snippets, content_to_lexical_score_list = multi_get_top_k_snippets(
        cloned_repo, [query], ticket_progress, k
    )
    return ranked_snippets_list[0], snippets, content_to_lexical_score_list[0]

@file_cache()
def cohere_rerank_call(
    query: str,
    documents: list[str],
    model='rerank-english-v3.0',
    **kwargs,
):
    # Cohere API call with caching
    co = cohere.Client(COHERE_API_KEY)
    return co.rerank(
        model=model,
        query=query,
        documents=documents,
        **kwargs
    )

def get_pointwise_reranked_snippet_scores(
    query: str,
    snippets: list[Snippet],
    snippet_scores: dict[str, float],
):
    """
    Ranks 1-5 snippets are frozen. They're just passed into Cohere since it helps with reranking. We multiply the scores by 1_000 to make them more significant.
    Ranks 6-100 are reranked using Cohere. Then we divide the scores by 1_000 to make them comparable to the original scores.
    """

    if not COHERE_API_KEY:
        return snippet_scores

    sorted_snippets = sorted(
        snippets,
        key=lambda snippet: snippet_scores[snippet.denotation],
        reverse=True,
    )

    NUM_SNIPPETS_TO_KEEP = 5
    NUM_SNIPPETS_TO_RERANK = 100

    response = cohere_rerank_call(
        model='rerank-english-v3.0',
        query=query,
        documents=[snippet.xml for snippet in sorted_snippets[:NUM_SNIPPETS_TO_RERANK]],
        max_chunks_per_doc=900 // NUM_SNIPPETS_TO_RERANK,
    )

    new_snippet_scores = {k: v / 1000 for k, v in snippet_scores.items()}

    for document in response.results:
        new_snippet_scores[sorted_snippets[document.index].denotation] = apply_adjustment_score(
            sorted_snippets[document.index].denotation,
            document.relevance_score,
        )

    for snippet in sorted_snippets[:NUM_SNIPPETS_TO_KEEP]:
        new_snippet_scores[snippet.denotation] = snippet_scores[snippet.denotation] * 1_000
    
    return new_snippet_scores

def multi_prep_snippets(
    cloned_repo: ClonedRepo,
    queries: list[str],
    ticket_progress: TicketProgress | None = None,
    k: int = 15,
    skip_reranking: bool = False, # This is only for pointwise reranking
    skip_pointwise_reranking: bool = False,
) -> RepoContextManager:
    """
    Assume 0th index is the main query.
    """
    rank_fusion_offset = 0
    if len(queries) > 1:
        logger.info("Using multi query...")
        ranked_snippets_list, snippets, content_to_lexical_score_list = multi_get_top_k_snippets(
            cloned_repo, queries, ticket_progress, k * 3 # k * 3 to have enough snippets to rerank
        )
        # Use RRF to rerank snippets
        content_to_lexical_score = defaultdict(float)
        for i, ordered_snippets in enumerate(ranked_snippets_list):
            for j, snippet in enumerate(ordered_snippets):
                content_to_lexical_score[snippet.denotation] += content_to_lexical_score_list[i][snippet.denotation] * (1 / 2 ** (rank_fusion_offset + j))
        if not skip_pointwise_reranking:
            content_to_lexical_score = get_pointwise_reranked_snippet_scores(
                queries[0], snippets, content_to_lexical_score
            )
        ranked_snippets = sorted(
            snippets,
            key=lambda snippet: content_to_lexical_score[snippet.denotation],
            reverse=True,
        )[:k]
    else:
        ranked_snippets, snippets, content_to_lexical_score = get_top_k_snippets(
            cloned_repo, queries[0], ticket_progress, k
        )
        if not skip_pointwise_reranking:
            content_to_lexical_score = get_pointwise_reranked_snippet_scores(
                queries[0], snippets, content_to_lexical_score
            )
        ranked_snippets = sorted(
            snippets,
            key=lambda snippet: content_to_lexical_score[snippet.denotation],
            reverse=True,
        )[:k]
    if ticket_progress:
        ticket_progress.search_progress.retrieved_snippets = ranked_snippets
        ticket_progress.save()
    # you can use snippet.denotation and snippet.get_snippet()
    if not skip_reranking and not skip_pointwise_reranking:
        ranked_snippets[:NUM_SNIPPETS_TO_RERANK] = listwise_rerank_snippets(queries[0], ranked_snippets[:NUM_SNIPPETS_TO_RERANK])
    snippet_paths = [snippet.file_path for snippet in ranked_snippets]
    prefixes = []
    for snippet_path in snippet_paths:
        snippet_depth = len(snippet_path.split("/"))
        for idx in range(snippet_depth):  # heuristic
            if idx > snippet_depth // 2:
                prefixes.append("/".join(snippet_path.split("/")[:idx]) + "/")
        prefixes.append(snippet_path)
    _, dir_obj = cloned_repo.list_directory_tree(
        included_directories=list(set(prefixes)),
        included_files=list(set(snippet_paths)),
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

def prep_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    ticket_progress: TicketProgress | None = None,
    k: int = 15,
    skip_reranking: bool = False,
    use_multi_query: bool = True,
) -> RepoContextManager:
    if use_multi_query:
        queries = [query, *generate_multi_queries(query)]
    else:
        queries = [query]
    return multi_prep_snippets(
        cloned_repo, queries, ticket_progress, k, skip_reranking
    )

def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    seed: int = None,
    import_graph: nx.DiGraph = None,
    chat_logger = None,
) -> RepoContextManager:
    logger.info("Seed: " + str(seed))
    repo_context_manager = build_import_trees(
        repo_context_manager,
        import_graph,
    )
    repo_context_manager = add_relevant_files_to_top_snippets(repo_context_manager)
    repo_context_manager.dir_obj.add_relevant_files(
        repo_context_manager.relevant_file_paths
    )
    fcrs, plan = get_files_to_change(
        relevant_snippets=repo_context_manager.current_top_snippets,
        read_only_snippets=repo_context_manager.snippets,
        problem_statement=query,
        repo_name=repo_context_manager.cloned_repo.repo_full_name,
        import_graph=import_graph,
        chat_logger=chat_logger,
        seed=seed,
        context=True
    )
    repo_context_manager.file_change_requests = []
    for fcr in fcrs:
        try:
            content = repo_context_manager.cloned_repo.get_file_contents(fcr.filename)
        except FileNotFoundError:
            continue
        snippet = Snippet(
            file_path=fcr.filename,
            start=0,
            end=len(content.split("\n")),
            content=content,
        )
        repo_context_manager.file_change_requests.append(snippet)
    repo_context_manager.read_only_snippets = []
    if fcrs:
        for file_path in fcrs[0].relevant_files:
            try:
                content = repo_context_manager.cloned_repo.get_file_contents(file_path)
            except FileNotFoundError:
                continue
            snippet = Snippet(
                file_path=file_path,
                start=0,
                end=len(content.split("\n")),
                content=content,
            )
            repo_context_manager.read_only_snippets.append(snippet)
    else:
        raise Exception("No file change requests created.")
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

        repo_context_manager, import_graph = integrate_graph_retrieval(search_query, repo_context_manager)

        ticket_progress.search_progress.repo_tree = str(repo_context_manager.dir_obj)
        ticket_progress.save()
        repo_context_manager = get_relevant_context(
            formatted_query,
            repo_context_manager,
            ticket_progress,
            chat_logger=chat_logger,
            import_graph=import_graph,
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
    return snippets, tree, dir_obj, repo_context_manager


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

if __name__ == "__main__":
    from sweepai.utils.github_utils import MockClonedRepo

    cloned_repo = MockClonedRepo(
        _repo_dir="/tmp/sweep",
        repo_full_name="sweepai/sweep",
    )
    cloned_repo = MockClonedRepo(
        _repo_dir="/tmp/pulse-alp",
        repo_full_name="trilogy-group/pulse-alp",
    )
    rcm = prep_snippets(
        cloned_repo,
        # "I am trying to set up payment processing in my app using Stripe, but I keep getting a 400 error when I try to create a payment intent. I have checked the API key and the request body, but I can't figure out what's wrong. Here is the error message I'm getting: 'Invalid request: request parameters are invalid'. I have attached the relevant code snippets below. Can you help me find the part of the code that is causing this error?",
        "Where can I find the section that checks if assembly line workers are active or disabled?",
        use_multi_query=False,
        skip_reranking=True
    )
    breakpoint()