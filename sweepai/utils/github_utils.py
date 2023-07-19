import os
import re
import shutil
import time

import github
import modal
import requests
from github import Github
from github.Repository import Repository
from jwt import encode
from loguru import logger
from tqdm import tqdm

from sweepai.core.entities import Snippet
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.config.server import DB_MODAL_INST_NAME, GITHUB_APP_ID, GITHUB_APP_PEM
from sweepai.utils.ctags_chunker import get_ctags_for_file
from sweepai.utils.event_logger import posthog


def make_valid_string(string: str):
    pattern = r"[^\w./-]+"
    return re.sub(pattern, "_", string)


def get_jwt():
    signing_key = GITHUB_APP_PEM
    app_id = GITHUB_APP_ID
    payload = {"iat": int(time.time()), "exp": int(time.time()) + 600, "iss": app_id}

    return encode(payload, signing_key, algorithm="RS256")


def get_token(installation_id: int):
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
    return response.json()["token"]


def get_github_client(installation_id: int):
    token = get_token(installation_id)
    return Github(token)


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
    excluded_directories=None,
    included_files=None,
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

    def list_directory_contents(
        current_directory,
        indentation=""
    ):
        """Recursively list the contents of directories."""

        file_and_folder_names = os.listdir(current_directory)
        file_and_folder_names.sort()

        directory_tree_string = ""

        for name in file_and_folder_names:
            relative_path = os.path.join(current_directory, name)[len(root_directory) + 1:]
            if name in excluded_directories:
                continue
            complete_path = os.path.join(current_directory, name)

            if os.path.isdir(complete_path):
                if relative_path in included_directories:
                    directory_tree_string += f"{indentation}{relative_path}/\n"
                    directory_tree_string += list_directory_contents(
                        complete_path, indentation + "  "
                    )
                else:
                    directory_tree_string += f"{indentation}{name}/...\n"
            else:
                directory_tree_string += f"{indentation}{name}\n"
                if os.path.isfile(complete_path) and relative_path in included_files:
                    ctags = get_ctags_for_file(complete_path)
                    ctags = "\n".join([indentation + line for line in ctags.splitlines()])
                    if ctags.strip():
                        directory_tree_string += f"{ctags}\n"
        return directory_tree_string

    directory_tree = list_directory_contents(root_directory)
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
    files = [file[len(root_directory) + 1:] for file in files]
    return files

def get_tree_and_file_list(
        repo: Repository,
        installation_id: int,
        snippet_paths: list[str]
) -> str:
    from git import Repo
    token = get_token(installation_id)
    shutil.rmtree("repo", ignore_errors=True)
    repo_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
    git_repo = Repo.clone_from(repo_url, "repo")
    git_repo.git.checkout(SweepConfig.get_branch(repo))

    prefixes = []
    for snippet_path in snippet_paths:
        file_list = ""
        for directory in snippet_path.split("/")[:-1]:
            file_list += directory + "/"
            prefixes.append(file_list.rstrip("/"))
        file_list += snippet_path.split("/")[-1]
        prefixes.append(snippet_path)

    tree = list_directory_tree(
        "repo",
        included_directories=prefixes,
        included_files=snippet_paths,
    )
    file_list = get_file_list("repo")
    shutil.rmtree("repo")
    return tree, file_list


def get_file_contents(repo: Repository, file_path, ref=None):
    if ref is None:
        ref = repo.default_branch
    file = repo.get_contents(file_path, ref=ref)
    contents = file.decoded_content.decode("utf-8", errors='replace')
    return contents


def search_snippets(
        repo: Repository,
        query: str,
        installation_id: int,
        num_files: int = 5,
        include_tree: bool = True,
        branch: str = None,
        sweep_config: SweepConfig = SweepConfig(),
) -> tuple[list[Snippet], str]:
    # Initialize the relevant directories string
    get_relevant_snippets = modal.Function.lookup(DB_MODAL_INST_NAME, "get_relevant_snippets")
    snippets: list[Snippet] = get_relevant_snippets.call(
        repo.full_name, query, num_files, installation_id=installation_id
    )
    logger.info(f"Snippets: {snippets}")
    # TODO: We should prioritize the mentioned files
    for snippet in snippets:
        try:
            file_contents = get_file_contents(repo, snippet.file_path, ref=branch)
            if len(file_contents) > sweep_config.max_file_limit:  # more than ~10000 tokens
                logger.warning(f"Skipping {snippet.file_path}, too many tokens")
                continue
        except github.UnknownObjectException as e:
            logger.warning(f"Error: {e}")
            logger.warning(f"Skipping {snippet.file_path}")
        else:
            snippet.content = file_contents
    tree, file_list = get_tree_and_file_list(
        repo,
        installation_id,
        snippet_paths=[snippet.file_path for snippet in snippets]
    )
    for file_path in tqdm(file_list):
        if file_path in query:
            try:
                file_contents = get_file_contents(repo, file_path, ref=branch)
                if len(file_contents) > sweep_config.max_file_limit:  # more than 10000 tokens
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
        repo = get_github_client(installation_id).get_repo(repo_name)
        labels = repo.get_labels()
        label_names = [label.name for label in labels]

        if "sweep" not in label_names:
            repo.create_label(
                name="sweep",
                color="5320E7",
                description="Assigns Sweep to an issue or pull request.",
            )
    except Exception as e:
        posthog("index_full_repository", "failed", {"error": str(e)})
        logger.warning(
            "Adding label failed, probably because label already."
        )  # warn that the repo may already be indexed
    return num_indexed_docs
