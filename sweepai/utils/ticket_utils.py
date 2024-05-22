from collections import defaultdict
import copy
import traceback
from time import time

from loguru import logger
from tqdm import tqdm
import networkx as nx

from sweepai.utils.timer import Timer
from sweepai.agents.analyze_snippets import AnalyzeSnippetAgent
from sweepai.config.client import SweepConfig, get_blocked_dirs
from sweepai.config.server import COHERE_API_KEY
from sweepai.core.context_pruning import RepoContextManager, add_relevant_files_to_top_snippets, build_import_trees, integrate_graph_retrieval
from sweepai.core.entities import Snippet
from sweepai.core.lexical_search import (
    compute_vector_search_scores,
    prepare_lexical_search_index,
    search_index,
)
from sweepai.core.sweep_bot import context_get_files_to_change
from sweepai.dataclasses.separatedsnippets import SeparatedSnippets
from sweepai.utils.cohere_utils import cohere_rerank_call
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.multi_query import generate_multi_queries
from sweepai.utils.openai_listwise_reranker import listwise_rerank_snippets
from sweepai.utils.progress import TicketProgress
from sweepai.utils.tree_utils import DirectoryTree


# the order here matters as the first match is used
code_snippet_separation_features = {
    "tools": {
        "prefix": [".git/", ".github/", ".circleci/", ".travis/", ".jenkins/", "scripts/", "script/", "bin/"],
        "suffix": [".gitignore", ".dockerignore", "Dockerfile", "Makefile", "Rakefile", "Procfile", ".sh", ".bat", ".cmd"],
        "substring": [],
    },
    "junk": { # we will discard this and not show it to the LLM
        "prefix": ["node_modules/", ".venv/", "build/", "venv/", "patch/", "target/", "bin/", "obj/"],
        "suffix": [".cache", ".gradle", ".mvn", ".settings", ".lock", ".log", ".tmp", ".tmp/", ".tmp.lock", ".tmp.lock/"],
        "substring": [".egg-info", "package-lock.json", "yarn.lock", ".cache", ".gradle", ".mvn"],
    },
    "dependencies": {
        "prefix": [".", "config/", ".github/", "vendor/"],
        "suffix": [".cfg", ".ini", ".po", "package.json", ".toml", ".yaml", ".yml", "LICENSE", ".lock"],
        "substring": ["requirements", "pyproject", "Gemfile", "Cargo", "pom.xml", "build.gradle"],
    },
    "docs": {
        "prefix": ["doc", "example", "README", "CHANGELOG"],
        "suffix": [".txt", ".rst", ".md", ".html", ".1", ".adoc", ".rdoc"],
        "substring": [],
    },
    "tests": {
        "prefix": ["tests/", "test/", "spec/"],
        "suffix": [
            ".spec.ts", ".spec.js", ".test.ts", ".test.js",
            "_test.py", "_test.ts", "_test.js", "_test.go",
            "Test.java", "Tests.java", "Spec.java", "Specs.java",
            "_spec.rb", "_specs.rb", ".feature",
        ],
        "substring": ["tests/", "test/", "/test", "_test", "rspec", ".test"],
    },
} 
# otherwise it's tagged as source
# we can make a config category later for css, config.ts, config.js. so far config files aren't many.

type_to_percentile_floor = { # lower gets more snippets
    "tools": 0.3,
    "dependencies": 0.3,
    "docs": 0.3,
    "tests": 0.3,
    "source": 0.15, # very low floor for source code
}

type_to_score_floor = { # the lower, the more snippets. we set this higher for less used types
    "tools": 0.05,
    "dependencies": 0.025, # usually not matched, this won't hit often
    "docs": 0.30, # matched often, so we can set a high threshold
    "tests": 0.15, # matched often, so we can set a high threshold
    "source": 0.0, # very low floor for source code
}

type_to_result_count = {
    "tools": 5,
    "dependencies": 5,
    "docs": 5,
    "tests": 15,
    "source": 30,
}

def separate_snippets_by_type(snippets: list[Snippet]) -> SeparatedSnippets:
    separated_snippets = SeparatedSnippets()
    for snippet in snippets:
        for type_name, separation in code_snippet_separation_features.items():
            if any(snippet.file_path.startswith(prefix) for prefix in separation["prefix"]) or any(snippet.file_path.endswith(suffix) for suffix in separation["suffix"]) or any(substring in snippet.file_path for substring in separation["substring"]):
                separated_snippets.add_snippet(snippet, type_name)
                break
        else:
            separated_snippets.add_snippet(snippet, "source")
    return separated_snippets

def apply_adjustment_score(
    snippet_path: str,
    old_score: float,
):
    snippet_score = old_score
    file_path, *_ = snippet_path.rsplit(":", 1)
    file_path = file_path.lower()
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
VECTOR_SEARCH_WEIGHT = 1.5

# @file_cache()
def multi_get_top_k_snippets(
    cloned_repo: ClonedRepo,
    queries: list[str],
    ticket_progress: TicketProgress | None = None,
    k: int = 15,
    include_docs: bool = False,
    include_tests: bool = False,
    do_not_use_file_cache: bool = False, # added for review_pr
    *args,
    **kwargs,
):
    """
    Handles multiple queries at once now. Makes the vector search faster.
    """
    sweep_config: SweepConfig = SweepConfig()
    blocked_dirs = get_blocked_dirs(cloned_repo.repo)
    sweep_config.exclude_dirs += blocked_dirs
    with Timer() as timer:
        _, snippets, lexical_index = prepare_lexical_search_index(
            cloned_repo.cached_dir,
            sweep_config,
            ticket_progress,
            ref_name=f"{str(cloned_repo.git_repo.head.commit.hexsha)}",
            do_not_use_file_cache=do_not_use_file_cache
        )
    logger.info(f"Lexical search index took {timer.time_elapsed} seconds")

    for snippet in snippets:
        snippet.file_path = snippet.file_path[len(cloned_repo.cached_dir) + 1 :]
    with Timer() as timer:
        content_to_lexical_score_list = [search_index(query, lexical_index) for query in queries]
    logger.info(f"Lexical search took {timer.time_elapsed} seconds")

    with Timer() as timer:
        files_to_scores_list = compute_vector_search_scores(queries, snippets)
    logger.info(f"Vector search took {timer.time_elapsed} seconds")

    for i, query in enumerate(queries):
        for snippet in tqdm(snippets):
            vector_score = files_to_scores_list[i].get(snippet.denotation, 0.04)
            snippet_score = 0.02
            if snippet.denotation in content_to_lexical_score_list[i]:
                # roughly fine tuned vector score weight based on average score
                # from search_eval.py on 50 test cases May 13th, 2024 on an internal benchmark
                snippet_score = (content_to_lexical_score_list[i][snippet.denotation] + (
                    vector_score * VECTOR_SEARCH_WEIGHT
                )) / (VECTOR_SEARCH_WEIGHT + 1)
                content_to_lexical_score_list[i][snippet.denotation] = snippet_score
            else:
                content_to_lexical_score_list[i][snippet.denotation] = snippet_score * vector_score
            content_to_lexical_score_list[i][snippet.denotation] = apply_adjustment_score(
                snippet_path=snippet.denotation, old_score=content_to_lexical_score_list[i][snippet.denotation]
            )
    
    ranked_snippets_list = [
        sorted(
            snippets,
            key=lambda snippet: content_to_lexical_score[snippet.denotation],
            reverse=True,
        )[:k] for content_to_lexical_score in content_to_lexical_score_list
    ]
    return ranked_snippets_list, snippets, content_to_lexical_score_list

# @file_cache()
def get_top_k_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    ticket_progress: TicketProgress | None = None,
    k: int = 15,
    do_not_use_file_cache: bool = False, # added for review_pr
    *args,
    **kwargs,
):
    ranked_snippets_list, snippets, content_to_lexical_score_list = multi_get_top_k_snippets(
        cloned_repo, [query], ticket_progress, k, do_not_use_file_cache=do_not_use_file_cache, *args, **kwargs
    )
    return ranked_snippets_list[0], snippets, content_to_lexical_score_list[0]

def get_pointwise_reranked_snippet_scores(
    query: str,
    snippets: list[Snippet],
    snippet_scores: dict[str, float],
    NUM_SNIPPETS_TO_KEEP=5,
    NUM_SNIPPETS_TO_RERANK=100,
    directory_summaries: dict = {},
):
    """
    Ranks 1-5 snippets are frozen. They're just passed into Cohere since it helps with reranking. We multiply the scores by 1_000 to make them more significant.
    Ranks 6-100 are reranked using Cohere. Then we divide the scores by 1_000_000 to make them comparable to the original scores.
    """

    if not COHERE_API_KEY:
        return snippet_scores

    sorted_snippets = sorted(
        snippets,
        key=lambda snippet: snippet_scores[snippet.denotation],
        reverse=True,
    )

    snippet_representations = []
    for snippet in sorted_snippets[:NUM_SNIPPETS_TO_RERANK]:
        representation = f"{snippet.file_path}\n```\n{snippet.get_snippet(add_lines=False, add_ellipsis=False)}\n```"
        subdirs = []
        for subdir in directory_summaries:
            if snippet.file_path.startswith(subdir):
                subdirs.append(subdir)
        subdirs = sorted(subdirs)
        for subdir in subdirs[-1:]:
            representation = representation + f"\n\nHere is a summary of the subdirectory {subdir}:\n\n" + directory_summaries[subdir]
        snippet_representations.append(representation)

    response = cohere_rerank_call(
        model='rerank-english-v3.0',
        query=query,
        documents=snippet_representations,
        max_chunks_per_doc=900 // NUM_SNIPPETS_TO_RERANK,
    )

    new_snippet_scores = {k: v / 1_000_000 for k, v in snippet_scores.items()}

    for document in response.results:
        new_snippet_scores[sorted_snippets[document.index].denotation] = apply_adjustment_score(
            snippet_path=sorted_snippets[document.index].denotation,
            old_score=document.relevance_score,
        )

    for snippet in sorted_snippets[:NUM_SNIPPETS_TO_KEEP]:
        new_snippet_scores[snippet.denotation] = snippet_scores[snippet.denotation] * 1_000
    
    # override score with Cohere score
    for snippet in sorted_snippets[:NUM_SNIPPETS_TO_RERANK]:
        if snippet.denotation in new_snippet_scores:
            snippet.score = new_snippet_scores[snippet.denotation]
    return new_snippet_scores

def multi_prep_snippets(
    cloned_repo: ClonedRepo,
    queries: list[str],
    ticket_progress: TicketProgress | None = None,
    k: int = 15,
    skip_reranking: bool = False, # This is only for pointwise reranking
    skip_pointwise_reranking: bool = False,
    NUM_SNIPPETS_TO_KEEP=0,
    NUM_SNIPPETS_TO_RERANK=100,
    include_docs: bool = False,
    include_tests: bool = False,
) -> RepoContextManager:
    """
    Assume 0th index is the main query.
    """
    if len(queries) > 1:
        rank_fusion_offset = 0
        logger.info("Using multi query...")
        ranked_snippets_list, snippets, content_to_lexical_score_list = multi_get_top_k_snippets(
            cloned_repo, queries, ticket_progress, k * 3, include_docs, include_tests # k * 3 to have enough snippets to rerank
        )
        # Use RRF to rerank snippets
        content_to_lexical_score = defaultdict(float)
        for i, ordered_snippets in enumerate(ranked_snippets_list):
            for j, snippet in enumerate(ordered_snippets):
                content_to_lexical_score[snippet.denotation] += content_to_lexical_score_list[i][snippet.denotation] * (1 / 2 ** (rank_fusion_offset + j))
    else:
        ranked_snippets, snippets, content_to_lexical_score = get_top_k_snippets(
            cloned_repo, queries[0], ticket_progress, k, include_docs, include_tests
        )
    separated_snippets = separate_snippets_by_type(snippets)
    if not skip_pointwise_reranking:
        all_snippets = []
        for type_name, snippets_subset in separated_snippets:
            if type_name == "junk":
                continue
            if len(snippets_subset) == 0:
                continue
            directory_summaries = {} # recursively_summarize_directory(snippets, cloned_repo)
            new_content_to_lexical_scores = get_pointwise_reranked_snippet_scores(
                queries[0], snippets_subset, content_to_lexical_score, NUM_SNIPPETS_TO_KEEP, NUM_SNIPPETS_TO_RERANK, directory_summaries
            )
            # set all keys of new_content_to_lexical_scores to content_to_lexical_score
            for key in new_content_to_lexical_scores:
                content_to_lexical_score[key] = new_content_to_lexical_scores[key]
            snippets_subset = sorted(
                snippets_subset,
                key=lambda snippet: new_content_to_lexical_scores[snippet.denotation],
                reverse=True,
            )
            separated_snippets.override_list(attribute_name=type_name, new_list=snippets_subset)
            logger.info(f"Reranked {type_name}")
            # cutoff snippets at percentile
            logger.info("Kept these snippets")
            if not snippets_subset:
                continue
            top_score = snippets_subset[0].score
            max_results = type_to_result_count[type_name]
            filtered_subset_snippets = []
            for idx, snippet in enumerate(snippets_subset[:max_results]):
                percentile = 0 if top_score == 0 else snippet.score / top_score
                if percentile < type_to_percentile_floor[type_name] or snippet.score < type_to_score_floor[type_name]:
                    break 
                logger.info(f"{idx}: {snippet.denotation} {snippet.score} {percentile}")
                snippet.type_name = type_name
                filtered_subset_snippets.append(snippet)
            if type_name != "source" and filtered_subset_snippets: # do more filtering
                filtered_subset_snippets = AnalyzeSnippetAgent().analyze_snippets(filtered_subset_snippets, type_name, queries[0])
            all_snippets.extend(filtered_subset_snippets)
        ranked_snippets = all_snippets[:k]
    else:
        ranked_snippets = sorted(
            snippets,
            key=lambda snippet: content_to_lexical_score[snippet.denotation],
            reverse=True,
        )[:k]
    # you can use snippet.denotation and snippet.get_snippet()
    if not skip_reranking and skip_pointwise_reranking:
        ranked_snippets[:NUM_SNIPPETS_TO_RERANK] = listwise_rerank_snippets(queries[0], ranked_snippets[:NUM_SNIPPETS_TO_RERANK])
    dir_obj = DirectoryTree() # init dummy one for now, this shouldn't be used
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
    *args,
    **kwargs,
) -> RepoContextManager:
    if use_multi_query:
        queries = [query, *generate_multi_queries(query)]
    else:
        queries = [query]
    return multi_prep_snippets(
        cloned_repo, queries, ticket_progress, k, skip_reranking, *args, **kwargs
    )

def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    seed: int = None,
    import_graph: nx.DiGraph = None,
    chat_logger = None,
    images = None
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
    # Idea: make two passes, one with tests and one without
    # if editing source code only provide source code
    # if editing test provide both source and test code
    relevant_files, read_only_files = context_get_files_to_change(
        relevant_snippets=repo_context_manager.current_top_snippets,
        read_only_snippets=repo_context_manager.read_only_snippets,
        problem_statement=query,
        repo_name=repo_context_manager.cloned_repo.repo_full_name,
        import_graph=import_graph,
        chat_logger=chat_logger,
        seed=seed,
        cloned_repo=repo_context_manager.cloned_repo,
        images=images
    )
    previous_top_snippets = copy.deepcopy(repo_context_manager.current_top_snippets)
    previous_read_only_snippets = copy.deepcopy(repo_context_manager.read_only_snippets)
    repo_context_manager.current_top_snippets = []
    repo_context_manager.read_only_snippets = []
    for relevant_file in relevant_files:
        try:
            content = repo_context_manager.cloned_repo.get_file_contents(relevant_file)
        except FileNotFoundError:
            continue
        snippet = Snippet(
            file_path=relevant_file,
            start=0,
            end=len(content.split("\n")),
            content=content,
        )
        repo_context_manager.current_top_snippets.append(snippet)
    for read_only_file in read_only_files:
        try:
            content = repo_context_manager.cloned_repo.get_file_contents(read_only_file)
        except FileNotFoundError:
            continue
        snippet = Snippet(
            file_path=read_only_file,
            start=0,
            end=len(content.split("\n")),
            content=content,
        )
        repo_context_manager.read_only_snippets.append(snippet)
    
    if not repo_context_manager.current_top_snippets and not repo_context_manager.read_only_snippets:
        repo_context_manager.current_top_snippets = copy.deepcopy(previous_top_snippets)
        repo_context_manager.read_only_snippets = copy.deepcopy(previous_read_only_snippets)
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
    issue_url,
    chat_logger,
    images = None
):
    logger.info("Fetching relevant files...")
    try:
        search_query = (title + summary + replies_text).strip("\n")
        replies_text = f"\n{replies_text}" if replies_text else ""
        formatted_query = (f"{title.strip()}\n{summary.strip()}" + replies_text).strip(
            "\n"
        )
        ticket_progress = None # refactor later
        repo_context_manager = prep_snippets(cloned_repo, search_query, ticket_progress)

        repo_context_manager, import_graph = integrate_graph_retrieval(search_query, repo_context_manager)

        repo_context_manager = get_relevant_context(
            formatted_query,
            repo_context_manager,
            ticket_progress,
            chat_logger=chat_logger,
            import_graph=import_graph,
            images=images
        )
        snippets = repo_context_manager.current_top_snippets
        dir_obj = repo_context_manager.dir_obj
        tree = str(dir_obj)
    except Exception as e:
        trace = traceback.format_exc()
        logger.exception(f"{trace} (tracking ID: `{tracking_id}`)")
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

    return wrapper

if __name__ == "__main__":
    from sweepai.utils.github_utils import MockClonedRepo
    from sweepai.utils.timer import Timer
    cloned_repo = MockClonedRepo(
        _repo_dir="/mnt/langchain",
        repo_full_name="langchain-ai/langchain",
    )

    with Timer() as timer:
        ranked_snippets, snippets, content_to_lexical_score = get_top_k_snippets(
            cloned_repo,
            "How does caching work in this repo?",
            None,
            15,
            False,
            False
        )
    print("Time taken:", timer.time_elapsed)
    breakpoint()