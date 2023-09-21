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


def get_snippets_for_query(cloned_repo: ClonedRepo, query: str, num_files: int) -> list[Snippet]:
    snippets: list[Snippet] = get_relevant_snippets(
        cloned_repo,
        query,
        num_files,
    )
    logger.info(f"Snippets for query {query}: {snippets}")
    return snippets

def get_file_contents_and_check_limit(cloned_repo: ClonedRepo, snippet: Snippet, sweep_config: SweepConfig) -> str:
    try:
        file_contents = cloned_repo.get_file_contents(snippet.file_path)
    except SystemExit:
        raise SystemExit
    except:
        return None
    try:
        if len(file_contents) > sweep_config.max_file_limit:  # more than ~10000 tokens
            logger.warning(f"Skipping {snippet.file_path}, too many tokens")
            return None
    except github.UnknownObjectException as e:
        logger.warning(f"Error: {e}")
        logger.warning(f"Skipping {snippet.file_path}")
        return None
    else:
        return file_contents

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
            snippets = get_snippets_for_query(cloned_repo, query, num_files)
            if snippets:
                lists_of_snippets.append(snippets)
        snippets = merge_and_dedup_snippets(lists_of_snippets)
        logger.info(f"Snippets for multi query {multi_query}: {snippets}")
    else:
        snippets = get_snippets_for_query(cloned_repo, query, num_files)

    new_snippets = []
    for snippet in snippets:
        file_contents = get_file_contents_and_check_limit(cloned_repo, snippet, sweep_config)
        if file_contents is not None:
            snippet.content = file_contents
            new_snippets.append(snippet)
    snippets = new_snippets
    from git import Repo

    # Rest of the function remains the same


def index_full_repository(
    repo_name: str,
    installation_id: int = None,
):
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
    except github.GithubException as e:
        if e.status == 422:  # label already exists
            logger.warning(
                "Adding label failed, probably because label already exists."
            )
        else:
            posthog.capture("index_full_repository", "failed", {"error": str(e)})
    except Exception as e:
        posthog.capture("index_full_repository", "failed", {"error": str(e)})
    return num_indexed_docs
