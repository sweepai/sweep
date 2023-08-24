import os
import re
import shutil
import time

import github
import modal
from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
import requests
from github import Github
from github.Repository import Repository
from jwt import encode
from loguru import logger
from tqdm import tqdm

from sweepai.core.entities import Snippet
from sweepai.config.client import SweepConfig
from sweepai.config.server import (
    DB_MODAL_INST_NAME,
    GITHUB_APP_ID,
    GITHUB_APP_PEM,
    REDIS_URL,
)
from sweepai.utils.ctags import CTags
from sweepai.utils.ctags_chunker import get_ctags_for_file, get_ctags_for_search
from sweepai.utils.event_logger import posthog
from sweepai.utils.scorer import merge_and_dedup_snippets
from rapidfuzz import fuzz

MAX_FILE_COUNT = 50


def make_valid_string(string: str):
    pattern = r"[^\w./-]+"
    return re.sub(pattern, "_", string)


def get_jwt():
    signing_key = GITHUB_APP_PEM
    app_id = GITHUB_APP_ID
    print(app_id)
    payload = {"iat": int(time.time()), "exp": int(time.time()) + 600, "iss": app_id}
    return encode(payload, signing_key, algorithm="RS256")


def get_token(installation_id: int):
    for timeout in [5.5, 5.5, 10.5]:
        try:
            jwt = get_jwt()
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + jwt,
                "X-GitHub-Api-Version": "2022-11-28",
            }
            response = requests.post(
                f"https://api.github.com/app/installations/{int(installation_id)}/access_tokens",
                headers=headers,
            )
            obj = response.json()
            if "token" not in obj:
                logger.error(obj)
                raise Exception("Could not get token")
            return obj["token"]
        except Exception as e:
            logger.error(e)
            time.sleep(timeout)
    raise Exception("Could not get token")


def get_github_client(installation_id: int):
    token = get_token(installation_id)
    return token, Github(token)


def get_installation_id(username: str):
    jwt = get_jwt()
    response = requests.get(
        f"https://api.github.com/users/{username}/installation",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + jwt,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    obj = response.json()
    try:
        return obj["id"]
    except:
        raise Exception("Could not get installation id, probably not installed")


def list_directory_tree(
    root_directory,
    included_directories=None,
    excluded_directories: list[str] = None,
    included_files=None,
    ctags: CTags = None,
):
    """Display the directory tree.

    Arguments:
    root_directory -- String path of the root directory to display.
    included_directories -- List of directory paths (relative to the root) to include in the tree. Default to None.
    excluded_directories -- List of directory names to exclude from the tree. Default to None.
    """

    # Default values if parameters are not provided
    if included_directories is None:
        included_directories = []
    if excluded_directories is None:
        excluded_directories = [".git"]
    else:
        excluded_directories.append(".git")

    def list_directory_contents(
        current_directory,
        indentation="",
        ctags: CTags = None,
    ):
        """Recursively list the contents of directories."""

        file_and_folder_names = os.listdir(current_directory)
        file_and_folder_names.sort()

        directory_tree_string = ""

        for name in file_and_folder_names[:MAX_FILE_COUNT]:
            relative_path = os.path.join(current_directory, name)[
                len(root_directory) + 1 :
            ]
            if name in excluded_directories:
                continue
            complete_path = os.path.join(current_directory, name)

            if os.path.isdir(complete_path):
                if relative_path in included_directories:
                    directory_tree_string += f"{indentation}{relative_path}/\n"
                    directory_tree_string += list_directory_contents(
                        complete_path, indentation + "  ", ctags=ctags
                    )
                else:
                    directory_tree_string += f"{indentation}{name}/...\n"
            else:
                directory_tree_string += f"{indentation}{name}\n"
                # if os.path.isfile(complete_path) and relative_path in included_files:
                #     # Todo, use these to fetch neighbors
                #     ctags_str, names = get_ctags_for_file(ctags, complete_path)
                #     ctags_str = "\n".join([indentation + line for line in ctags_str.splitlines()])
                #     if ctags_str.strip():
                #         directory_tree_string += f"{ctags_str}\n"
        return directory_tree_string

    directory_tree = list_directory_contents(root_directory, ctags=ctags)
    return directory_tree


def get_file_list(root_directory: str) -> str:
    files = []

    def dfs_helper(directory):
        nonlocal files
        for item in os.listdir(directory):
            if item == ".git":
                continue
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path):
                files.append(item_path)  # Add the file to the list
            elif os.path.isdir(item_path):
                dfs_helper(item_path)  # Recursive call to explore subdirectory

    dfs_helper(root_directory)
    files = [file[len(root_directory) + 1 :] for file in files]
    return files


def get_tree_and_file_list(
    repo: Repository,
    installation_id: int,
    snippet_paths: list[str],
    excluded_directories: list[str] = None,
) -> str:
    prefixes = []
    for snippet_path in snippet_paths:
        file_list = ""
        for directory in snippet_path.split("/")[:-1]:
            file_list += directory + "/"
            prefixes.append(file_list.rstrip("/"))
        file_list += snippet_path.split("/")[-1]
        prefixes.append(snippet_path)

    sha = repo.get_branch(repo.default_branch).commit.sha
    retry = Retry(ExponentialBackoff(), 3)
    cache_inst = Redis.from_url(
        REDIS_URL,
        retry=retry,
        retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError],
    )
    ctags = CTags(sha=sha, redis_instance=cache_inst)
    all_names = []
    for file in snippet_paths:
        ctags_str, names = get_ctags_for_file(ctags, os.path.join("repo", file))
        all_names.extend(names)
    tree = list_directory_tree(
        "repo",
        included_directories=prefixes,
        included_files=snippet_paths,
        excluded_directories=excluded_directories,
        ctags=ctags,
    )
    return tree


def get_file_contents(repo: Repository, file_path, ref=None):
    if ref is None:
        ref = repo.default_branch
    file = repo.get_contents(file_path, ref=ref)
    contents = file.decoded_content.decode("utf-8", errors="replace")
    return contents


def get_file_names_from_query(query: str) -> list[str]:
    query_file_names = re.findall(r"\b[\w\-\.\/]*\w+\.\w{1,6}\b", query)
    return [
        query_file_name
        for query_file_name in query_file_names
        if len(query_file_name) > 3
    ]


def get_num_files_from_repo(repo: Repository, installation_id: str):
    from git import Repo

    token = get_token(installation_id)
    shutil.rmtree("repo", ignore_errors=True)
    repo_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
    git_repo = Repo.clone_from(repo_url, "repo")
    git_repo.git.checkout(SweepConfig.get_branch(repo))
    file_list = get_file_list("repo")
    return len(file_list)


def get_top_match_ctags(repo, file_list, query):
    retry = Retry(ExponentialBackoff(), 3)
    cache_inst = Redis.from_url(
        REDIS_URL,
        retry=retry,
        retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError],
    )
    sha = repo.get_branch(repo.default_branch).commit.sha
    ctags = CTags(sha=sha, redis_instance=cache_inst)
    ctags_to_file = {}
    name_counts = {}
    for file in file_list:
        if file.endswith(".md") or file.endswith(".svg") or file.endswith(".png"):
            continue
        _, names = get_ctags_for_search(ctags, os.path.join("repo", file))
        for name in names:
            if name not in name_counts:
                name_counts[name] = 0
            name_counts[name] += 1
        names = " ".join(names)  # counts here, compute tf-idf
        ctags_to_file[names] = file
    ctags_score = []
    for names, file in ctags_to_file.items():
        score = fuzz.ratio(query, names)
        ctags_score.append((score, file))
    ctags_score.sort(key=lambda x: x[0], reverse=True)

    if len(ctags_score) > 0:
        top_match = ctags_score[0]
        return top_match[1] if top_match[0] > 40 else None


def search_snippets(
    repo: Repository,
    query: str,
    installation_id: int,
    num_files: int = 5,
    include_tree: bool = True,
    branch: str = None,
    sweep_config: SweepConfig = SweepConfig(),
    multi_query: list[str] = None,
    excluded_directories: list[str] = None,
) -> tuple[list[Snippet], str]:
    # Initialize the relevant directories string
    get_relevant_snippets = modal.Function.lookup(
        DB_MODAL_INST_NAME, "get_relevant_snippets"
    )
    if multi_query:
        lists_of_snippets = list[list[Snippet]]()
        multi_query = [query] + multi_query
        for query in multi_query:
            snippets: list[Snippet] = get_relevant_snippets.call(
                repo.full_name, query, num_files, installation_id=installation_id
            )
            logger.info(f"Snippets for query {query}: {snippets}")
            if snippets:
                lists_of_snippets.append(snippets)
        snippets = merge_and_dedup_snippets(lists_of_snippets)
        logger.info(f"Snippets for multi query {multi_query}: {snippets}")
    else:
        snippets: list[Snippet] = get_relevant_snippets.call(
            repo.full_name, query, num_files, installation_id=installation_id
        )
        logger.info(f"Snippets for query {query}: {snippets}")
    new_snippets = []
    for snippet in snippets:
        try:
            file_contents = get_file_contents(repo, snippet.file_path, ref=branch)
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

    token = get_token(installation_id)
    shutil.rmtree("repo", ignore_errors=True)
    repo_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
    git_repo = Repo.clone_from(repo_url, "repo")
    git_repo.git.checkout(SweepConfig.get_branch(repo))
    file_list = get_file_list("repo")
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
    tree = get_tree_and_file_list(
        repo,
        installation_id,
        snippet_paths=snippet_paths,
        excluded_directories=excluded_directories,
    )
    # Add top ctags match to snippets
    # if top_ctags_match and top_ctags_match not in query_match_files:
    #     query_match_files = [top_ctags_match] + query_match_files
    #     print(f"Top ctags match: {top_ctags_match}")
    for file_path in query_match_files:
        try:
            file_contents = get_file_contents(repo, file_path, ref=branch)
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
    if include_tree:
        return snippets, tree
    else:
        return snippets


def index_full_repository(
    repo_name: str,
    installation_id: int = None,
    sweep_config: SweepConfig = SweepConfig(),
):
    update_index = modal.Function.lookup(DB_MODAL_INST_NAME, "update_index")
    num_indexed_docs = update_index.spawn(
        repo_name=repo_name,
        installation_id=installation_id,
        sweep_config=sweep_config,
    )
    try:
        repo = (get_github_client(installation_id)[1]).get_repo(repo_name)
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
