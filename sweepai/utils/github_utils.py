import datetime
import difflib
import hashlib
import os
import re
import shutil
import subprocess
import time
import traceback
from dataclasses import dataclass
from functools import cached_property

import git
import requests
from github import Github
from jwt import encode
from redis import Redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from redis.retry import Retry

from sweepai.config.client import SweepConfig
from sweepai.config.server import GITHUB_APP_ID, GITHUB_APP_PEM, REDIS_URL
from sweepai.logn import logger
from sweepai.utils.ctags import CTags
from sweepai.utils.ctags_chunker import get_ctags_for_file
from sweepai.utils.tree_utils import DirectoryTree

MAX_FILE_COUNT = 50


def make_valid_string(string: str):
    pattern = r"[^\w./-]+"
    return re.sub(pattern, "_", string)


def get_jwt():
    signing_key = GITHUB_APP_PEM
    app_id = GITHUB_APP_ID
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
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(e)
            time.sleep(timeout)
    raise Exception(
        "Could not get token, please double check your PRIVATE_KEY and GITHUB_APP_ID in the .env file. Make sure to restart uvicorn after."
    )


def get_github_client(installation_id: int):
    token: str = get_token(installation_id)
    return token, Github(token)


def get_installation_id(username: str) -> str:
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
    except SystemExit:
        raise SystemExit
    except:
        raise Exception("Could not get installation id, probably not installed")


@dataclass
class ClonedRepo:
    repo_full_name: str
    installation_id: str
    branch: str | None = None
    token: str | None = None

    @cached_property
    def cache_dir(self):
        random_bytes = os.urandom(16)
        hash_obj = hashlib.sha256(random_bytes)
        hash_hex = hash_obj.hexdigest()
        if self.branch:
            return os.path.join(
                "/tmp/cache/repos",
                self.repo_full_name,
                hash_hex,
                self.branch,
            )
        else:
            return os.path.join("/tmp/cache/repos", self.repo_full_name, hash_hex)

    @property
    def clone_url(self):
        return (
            f"https://x-access-token:{self.token}@github.com/{self.repo_full_name}.git"
        )

    def clone(self):
        if self.branch:
            return git.Repo.clone_from(
                self.clone_url, self.cache_dir, branch=self.branch
            )
        else:
            return git.Repo.clone_from(self.clone_url, self.cache_dir)

    def __post_init__(self):
        subprocess.run(["git", "config", "--global", "http.postBuffer", "524288000"])
        self.token = self.token or get_token(self.installation_id)
        if os.path.exists(self.cache_dir):
            self.git_repo = git.Repo(self.cache_dir)
            try:
                self.git_repo.remotes.origin.pull()
            except SystemExit:
                raise SystemExit
            except:
                logger.error("Could not pull repo")
                self.git_repo = self.clone()
        self.git_repo = self.clone()
        self.repo = Github(self.token).get_repo(self.repo_full_name)
        self.branch = self.branch or SweepConfig.get_branch(self.repo)

    def delete(self):
        shutil.rmtree(self.cache_dir)

    def list_directory_tree(
        self,
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

        root_directory = self.cache_dir

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

        dir_obj = DirectoryTree()
        directory_tree = list_directory_contents(root_directory, ctags=ctags)
        dir_obj.parse(directory_tree)
        return directory_tree, dir_obj

    def get_file_list(self) -> str:
        root_directory = self.cache_dir
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
        self,
        snippet_paths: list[str],
        excluded_directories: list[str] = None,
    ) -> tuple[str, DirectoryTree]:
        prefixes = []
        for snippet_path in snippet_paths:
            file_list = ""
            for directory in snippet_path.split("/")[:-1]:
                file_list += directory + "/"
                prefixes.append(file_list.rstrip("/"))
            file_list += snippet_path.split("/")[-1]
            prefixes.append(snippet_path)

        retry = Retry(ExponentialBackoff(), 3)
        cache_inst = (
            Redis.from_url(
                REDIS_URL,
                retry=retry,
                retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError],
            )
            if REDIS_URL
            else None
        )
        ctags = CTags(redis_instance=cache_inst)
        all_names = []
        for file in snippet_paths:
            _, names = get_ctags_for_file(ctags, os.path.join("repo", file))
            all_names.extend(names)
        tree, dir_obj = self.list_directory_tree(
            included_directories=prefixes,
            included_files=snippet_paths,
            excluded_directories=excluded_directories,
            ctags=ctags,
        )
        return tree, dir_obj

    def get_file_contents(self, file_path, ref=None):
        local_path = os.path.join(self.cache_dir, file_path)
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                contents = f.read()
            return contents
        else:
            raise FileNotFoundError(f"{local_path} does not exist.")

    def get_num_files_from_repo(self):
        # subprocess.run(["git", "config", "--global", "http.postBuffer", "524288000"])
        self.git_repo.git.checkout(self.branch)
        file_list = self.get_file_list()
        return len(file_list)

    def get_commit_history(
        self, username: str = "", limit: int = 200, time_limited: bool = True
    ):
        commit_history = []
        try:
            if username != "":
                commit_list = list(self.git_repo.iter_commits(author=username))
            else:
                commit_list = list(self.git_repo.iter_commits())
            line_count = 0
            cut_off_date = datetime.datetime.now() - datetime.timedelta(days=7)
            for commit in commit_list:
                # must be within a week
                if time_limited and commit.authored_datetime.replace(
                    tzinfo=None
                ) <= cut_off_date.replace(tzinfo=None):
                    logger.info(f"Exceeded cut off date, stopping...")
                    break
                repo = get_github_client(self.installation_id)[1].get_repo(
                    self.repo_full_name
                )
                branch = SweepConfig.get_branch(repo)
                if branch not in self.git_repo.git.branch():
                    branch = f"origin/{branch}"
                diff = self.git_repo.git.diff(commit, branch, unified=1)
                lines = diff.count("\n")
                # total diff lines must not exceed 200
                if lines + line_count > limit:
                    logger.info(f"Exceeded {limit} lines of diff, stopping...")
                    break
                commit_history.append(
                    f"<commit>\nAuthor: {commit.author.name}\nMessage: {commit.message}\n{diff}\n</commit>"
                )
                line_count += lines
        except:
            logger.error(f"An error occurred: {traceback.print_exc()}")
        return commit_history


def get_file_names_from_query(query: str) -> list[str]:
    query_file_names = re.findall(r"\b[\w\-\.\/]*\w+\.\w{1,6}\b", query)
    return [
        query_file_name
        for query_file_name in query_file_names
        if len(query_file_name) > 3
    ]


def get_hunks(a: str, b: str, context=10):
    differ = difflib.Differ()
    diff = [
        line
        for line in differ.compare(a.splitlines(), b.splitlines())
        if line[0] in ("+", "-", " ")
    ]

    show = set()
    hunks = []

    for i, line in enumerate(diff):
        if line.startswith(("+", "-")):
            show.update(range(max(0, i - context), min(len(diff), i + context + 1)))

    for i in range(len(diff)):
        if i in show:
            hunks.append(diff[i])
        elif i - 1 in show:
            hunks.append("...")

    if len(hunks) > 0 and hunks[0] == "...":
        hunks = hunks[1:]
    if len(hunks) > 0 and hunks[-1] == "...":
        hunks = hunks[:-1]

    return "\n".join(hunks)


str1 = "a\nline1\nline2\nline3\nline4\nline5\nline6\ntest\n"
str2 = "a\nline1\nlineTwo\nline3\nline4\nline5\nlineSix\ntset\n"

if __name__ == "__main__":
    print(get_hunks(str1, str2, 1))
