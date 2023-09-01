import shutil
import subprocess
import github
from loguru import logger

from github.Repository import Repository
from tqdm import tqdm

from sweepai.config.client import SweepConfig
from sweepai.core.vector_db import get_relevant_snippets, update_index
from sweepai.core.entities import Snippet
from sweepai.utils.github_utils import (
    ClonedRepo,
    get_file_names_from_query,
    get_github_client,
)
from sweepai.utils.scorer import merge_and_dedup_snippets
from sweepai.utils.event_logger import posthog


def search_snippets(
    # repo: Repository,
    cloned_repo: ClonedRepo,
    query: str,
    # installation_id: int,
    num_files: int = 5,
    include_tree: bool = True,
    # branch: str = None,
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
                cloned_repo.repo_full_name,
                query,
                num_files,
                installation_id=cloned_repo.installation_id,
            )
            logger.info(f"Snippets for query {query}: {snippets}")
            if snippets:
                lists_of_snippets.append(snippets)
        snippets = merge_and_dedup_snippets(lists_of_snippets)
        logger.info(f"Snippets for multi query {multi_query}: {snippets}")
    else:
        snippets: list[Snippet] = get_relevant_snippets(
            cloned_repo.repo_full_name,
            query,
            num_files,
            installation_id=cloned_repo.installation_id,
        )
        logger.info(f"Snippets for query {query}: {snippets}")
    new_snippets = []
    for snippet in snippets:
        try:
            file_contents = cloned_repo.get_file_contents(snippet.file_path)
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

    # token = get_token(cloned_repo.installation_id)
    # shutil.rmtree("repo", ignore_errors=True)
    # repo_url = f"https://x-access-token:{token}@github.com/{cloned_repo.repo.full_name}.git"
    # Set a larger buffer size for large repos
    # subprocess.run(["git", "config", "--global", "http.postBuffer", "524288000"])
    # git_repo = Repo.clone_from(repo_url, "repo")
    # git_repo.git.checkout(SweepConfig.get_branch(cloned_repo.repo))
    # file_list = get_file_list("repo")
    file_list = cloned_repo.get_file_list()

    # top_ctags_match = get_top_match_ctags(repo, file_list, query)  # ctags match
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
    # tree = get_tree_and_file_list(
    #     cloned_repo.repo,
    #     cloned_repo.installation_id,
    #     snippet_paths=snippet_paths,
    #     excluded_directories=excluded_directories,
    # )
    tree = cloned_repo.get_tree_and_file_list(
        snippet_paths=snippet_paths, excluded_directories=excluded_directories
    )
    # Add top ctags match to snippets
    # if top_ctags_match and top_ctags_match not in query_match_files:
    #     query_match_files = [top_ctags_match] + query_match_files
    #     print(f"Top ctags match: {top_ctags_match}")
    for file_path in query_match_files:
        try:
            # file_contents = get_file_contents(cloned_repo.repo, file_path, ref=cloned_repo.branch)
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
    repo = get_github_client(installation_id).get_repo(repo_name)
    num_indexed_docs = update_index(
        repo_name=repo_name,
        installation_id=installation_id,
        sweep_config=SweepConfig.get_config(repo),
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
    except Exception as e:
        posthog.capture("index_full_repository", "failed", {"error": str(e)})
        logger.warning(
            "Adding label failed, probably because label already."
        )  # warn that the repo may already be indexed
    return num_indexed_docs
