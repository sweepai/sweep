import shutil
import subprocess
import github
from logn import logger, file_cache

from github.Repository import Repository
from tqdm import tqdm

from sweepai.config.client import SweepConfig
from sweepai.core.vector_db import get_deeplake_vs_from_repo, get_relevant_snippets
from sweepai.core.entities import Snippet
from sweepai.utils.github_utils import (
    ClonedRepo,
    get_file_names_from_query,
    get_github_client,
)
from sweepai.utils.scorer import merge_and_dedup_snippets
from sweepai.utils.event_logger import posthog


@file_cache(ignore_params=["cloned_repo", "sweep_config"])
def search_snippets(
    cloned_repo: ClonedRepo,
    query: str,
    num_files: int = 5,
    include_tree: bool = True,
    sweep_config: SweepConfig = SweepConfig(),
    multi_query: list[str] = None,
    excluded_directories: list[str] = None,
) -> tuple[list[Snippet], str]:
    # Initialize the relevant directories string
    if multi_query:
        lists_of_snippets = list[list[Snippet]]()
        multi_query = [query] + multi_query
        for query in multi_query:
            snippets: list[Snippet] = get_relevant_snippets(
                cloned_repo,
                query,
                num_files,
            )
            logger.info(f"Snippets for query {query}: {snippets}")
            if snippets:
                lists_of_snippets.append(snippets)
        snippets = merge_and_dedup_snippets(lists_of_snippets)
        logger.info(f"Snippets for multi query {multi_query}: {snippets}")
    else:
        snippets: list[Snippet] = get_relevant_snippets(
            cloned_repo,
            query,
            num_files,
        )
        logger.info(f"Snippets for query {query}: {snippets}")
    new_snippets = []
    for snippet in snippets:
        try:
            file_contents = cloned_repo.get_file_contents(snippet.file_path)
        except SystemExit:
            raise SystemExit
        except:
            continue
        try:
            if (
                len(file_contents) > sweep_config.max_file_limit
            ):  # more than ~10000 tokens
                logger.warning(f"Skipping {snippet.file_path}, too many tokens")
                continue
        except github.UnknownObjectException as e:
            logger.warning(f"Error: {e}")
            logger.warning(f"Skipping {snippet.file_path}")
        else:
            snippet.content = file_contents
            new_snippets.append(snippet)
    snippets = new_snippets
    from git import Repo

    file_list = cloned_repo.get_file_list()
    query_file_names = get_file_names_from_query(query)
    query_match_files = []  # files in both query and repo
    for file_path in tqdm(file_list):
        for query_file_name in query_file_names:
            if query_file_name in file_path:
                query_match_files.append(file_path)
    if multi_query:
        snippet_paths = [snippet.file_path for snippet in snippets] + query_match_files[
            :20
        ]
    else:
        snippet_paths = [snippet.file_path for snippet in snippets] + query_match_files[
            :10
        ]
    snippet_paths = list(set(snippet_paths))
    tree = cloned_repo.get_tree_and_file_list(
        snippet_paths=snippet_paths, excluded_directories=excluded_directories
    )
    for file_path in query_match_files:
        try:
            file_contents = cloned_repo.get_file_contents(
                file_path, ref=cloned_repo.branch
            )
            if (
                len(file_contents) > sweep_config.max_file_limit
            ):  # more than 10000 tokens
                logger.warning(f"Skipping {file_path}, too many tokens")
                continue
        except github.UnknownObjectException as e:
            logger.warning(f"Error: {e}")
            logger.warning(f"Skipping {file_path}")
        else:
            snippets = [
                Snippet(
                    content=file_contents,
                    start=0,
                    end=file_contents.count("\n") + 1,
                    file_path=file_path,
                )
            ] + snippets
    snippets = [snippet.expand() for snippet in snippets]
    logger.info(f"Tree: {tree}")
    logger.info(f"Snippets: {snippets}")
    if include_tree:
        return snippets, tree
    else:
        return snippets


def index_full_repository(
    repo_name: str,
    installation_id: int = None,
):
    # update_index = modal.Function.lookup(DB_MODAL_INST_NAME, "update_index")
    _token, client = get_github_client(installation_id)
    repo = client.get_repo(repo_name)
    cloned_repo = ClonedRepo(repo_name, installation_id=installation_id)
    _, _, num_indexed_docs = get_deeplake_vs_from_repo(
        cloned_repo=cloned_repo,
        sweep_config=SweepConfig.get_config(cloned_repo.repo),
    )
    try:
        labels = repo.get_labels()
        label_names = [label.name for label in labels]

        if "sweep" not in label_names:
            repo.create_label(
                name="sweep",
                color="5320E7",
                description="Assigns Sweep to an issue or pull request.",
            )
    except SystemExit:
        raise SystemExit
    except Exception as e:
        posthog.capture("index_full_repository", "failed", {"error": str(e)})
        logger.warning(
            "Adding label failed, probably because label already."
        )  # warn that the repo may already be indexed
    return num_indexed_docs
