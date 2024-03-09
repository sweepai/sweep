import datetime
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import traceback
from dataclasses import dataclass
from functools import cached_property
from typing import Any

import git
import requests
from github import Github, PullRequest
from jwt import encode
from loguru import logger

from sweepai.config.client import SweepConfig
from sweepai.config.server import GITHUB_APP_ID, GITHUB_APP_PEM, GITHUB_BOT_USERNAME
from sweepai.utils.tree_utils import DirectoryTree, remove_all_not_included

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
    if int(installation_id) < 0:
        return os.environ["GITHUB_PAT"]
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
        except Exception:
            time.sleep(timeout)
    raise Exception(
        "Could not get token, please double check your PRIVATE_KEY and GITHUB_APP_ID in the .env file. Make sure to restart uvicorn after."
    )


def get_app():
    jwt = get_jwt()
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + jwt,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.get("https://api.github.com/app", headers=headers)
    return response.json()


def get_github_client(installation_id: int):
    if not installation_id:
        return os.environ["GITHUB_PAT"], Github(os.environ["GITHUB_PAT"])
    token: str = get_token(installation_id)
    return token, Github(token)


def get_installation_id(username: str) -> str:
    jwt = get_jwt()
    try:
        # Try user
        response = requests.get(
            f"https://api.github.com/users/{username}/installation",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + jwt,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        obj = response.json()
        return obj["id"]
    except Exception:
        # Try org
        response = requests.get(
            f"https://api.github.com/orgs/{username}/installation",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + jwt,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            obj = response.json()
            return obj["id"]
        except Exception as e:
            logger.error(e)
            logger.error(response.text)
        raise Exception("Could not get installation id, probably not installed")


REPO_CACHE_BASE_DIR = "/tmp/cache/repos"


@dataclass
class ClonedRepo:
    repo_full_name: str
    installation_id: str
    branch: str | None = None
    token: str | None = None
    repo: Any | None = None
    git_repo: git.Repo | None = None

    class Config:
        arbitrary_types_allowed = True

    @cached_property
    def cached_dir(self):
        self.repo = (
            Github(self.token).get_repo(self.repo_full_name)
            if not self.repo
            else self.repo
        )
        self.branch = self.branch or SweepConfig.get_branch(self.repo)
        return os.path.join(
            REPO_CACHE_BASE_DIR,
            self.repo_full_name,
            "base",
            parse_collection_name(self.branch),
        )

    @cached_property
    def zip_path(self):
        logger.info("Zipping repository...")
        shutil.make_archive(self.repo_dir, "zip", self.repo_dir)
        logger.info("Done zipping")
        return f"{self.repo_dir}.zip"

    @cached_property
    def repo_dir(self):
        self.repo = (
            Github(self.token).get_repo(self.repo_full_name)
            if not self.repo
            else self.repo
        )
        self.branch = self.branch or SweepConfig.get_branch(self.repo)
        curr_time_str = str(time.time()).encode("utf-8")
        hash_obj = hashlib.sha256(curr_time_str)
        hash_hex = hash_obj.hexdigest()
        if self.branch:
            return os.path.join(
                REPO_CACHE_BASE_DIR,
                self.repo_full_name,
                hash_hex,
                parse_collection_name(self.branch),
            )
        else:
            return os.path.join("/tmp/cache/repos", self.repo_full_name, hash_hex)

    @property
    def clone_url(self):
        return (
            f"https://x-access-token:{self.token}@github.com/{self.repo_full_name}.git"
        )

    def clone(self):
        if not os.path.exists(self.cached_dir):
            logger.info("Cloning repo...")
            if self.branch:
                repo = git.Repo.clone_from(
                    self.clone_url, self.cached_dir, branch=self.branch
                )
            else:
                repo = git.Repo.clone_from(self.clone_url, self.cached_dir)
            logger.info("Done cloning")
        else:
            try:
                repo = git.Repo(self.cached_dir)
                repo.remotes.origin.pull(
                    kill_after_timeout=60, progress=git.RemoteProgress()
                )
            except Exception:
                logger.error("Could not pull repo")
                shutil.rmtree(self.cached_dir, ignore_errors=True)
                repo = git.Repo.clone_from(self.clone_url, self.cached_dir)
            logger.info("Repo already cached, copying")
        logger.info("Copying repo...")
        shutil.copytree(
            self.cached_dir, self.repo_dir, symlinks=True, copy_function=shutil.copy
        )
        logger.info("Done copying")
        repo = git.Repo(self.repo_dir)
        return repo

    def __post_init__(self):
        subprocess.run(["git", "config", "--global", "http.postBuffer", "524288000"])
        self.token = self.token or get_token(self.installation_id)
        self.repo = (
            Github(self.token).get_repo(self.repo_full_name)
            if not self.repo
            else self.repo
        )
        self.commit_hash = self.repo.get_commits()[0].sha
        self.git_repo = self.clone()
        self.branch = self.branch or SweepConfig.get_branch(self.repo)

    def __del__(self):
        try:
            shutil.rmtree(self.repo_dir)
            os.remove(self.zip_path)
            return True
        except Exception:
            return False

    def list_directory_tree(
        self,
        included_directories=None,
        excluded_directories: list[str] = None,
        included_files=None,
    ):
        """Display the directory tree.

        Arguments:
        root_directory -- String path of the root directory to display.
        included_directories -- List of directory paths (relative to the root) to include in the tree. Default to None.
        excluded_directories -- List of directory names to exclude from the tree. Default to None.
        """

        root_directory = self.repo_dir
        sweep_config: SweepConfig = SweepConfig()

        # Default values if parameters are not provided
        if included_directories is None:
            included_directories = []  # gets all directories
        if excluded_directories is None:
            excluded_directories = sweep_config.exclude_dirs

        def list_directory_contents(
            current_directory: str,
            excluded_directories: list[str],
            indentation="",
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
                    directory_tree_string += f"{indentation}{relative_path}/\n"
                    directory_tree_string += list_directory_contents(
                        complete_path,
                        excluded_directories,
                        indentation + "  ",
                    )
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
        directory_tree = list_directory_contents(root_directory, excluded_directories)
        dir_obj.parse(directory_tree)
        if included_directories:
            dir_obj = remove_all_not_included(dir_obj, included_directories)
        return directory_tree, dir_obj

    def get_file_list(self) -> str:
        root_directory = self.repo_dir
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

    def get_file_contents(self, file_path, ref=None):
        local_path = (
            f"{self.repo_dir}{file_path}"
            if file_path.startswith("/")
            else f"{self.repo_dir}/{file_path}"
        )
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
                    logger.info("Exceeded cut off date, stopping...")
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
        except Exception:
            logger.error(f"An error occurred: {traceback.print_exc()}")
        return commit_history

    def get_similar_file_paths(self, file_path: str, limit: int = 10):
        from rapidfuzz.fuzz import ratio

        # Fuzzy search over file names
        file_name = os.path.basename(file_path)
        all_file_paths = self.get_file_list()
        files_with_matching_name = []
        files_without_matching_name = []
        for file_path in all_file_paths:
            if file_name in file_path:
                files_with_matching_name.append(file_path)
            else:
                files_without_matching_name.append(file_path)
        files_with_matching_name = sorted(
            files_with_matching_name,
            key=lambda file_path: ratio(file_name, file_path),
            reverse=True,
        )
        files_without_matching_name = sorted(
            files_without_matching_name,
            key=lambda file_path: ratio(file_name, file_path),
            reverse=True,
        )
        all_files = files_with_matching_name + files_without_matching_name
        return all_files[:limit]


@dataclass
class MockClonedRepo(ClonedRepo):
    _repo_dir: str = ""
    git_repo: git.Repo | None = None

    def __init__(
        self,
        _repo_dir: str,
        repo_full_name: str,
        installation_id: str = "",
        branch: str | None = None,
        token: str | None = None,
        repo: Any | None = None,
        git_repo: git.Repo | None = None,
    ):
        self._repo_dir = _repo_dir
        self.repo_full_name = repo_full_name
        self.installation_id = installation_id
        self.branch = branch
        self.token = token
        self.repo = repo

    @classmethod
    def from_dir(cls, repo_dir: str, **kwargs):
        return cls(_repo_dir=repo_dir, **kwargs)

    @property
    def cached_dir(self):
        return self._repo_dir

    @property
    def repo_dir(self):
        return self._repo_dir

    @property
    def git_repo(self):
        return git.Repo(self.repo_dir)

    def clone(self):
        return git.Repo(self.repo_dir)

    def __post_init__(self):
        return self

    def __del__(self):
        return True


@dataclass
class TemporarilyCopiedClonedRepo(MockClonedRepo):
    tmp_dir: tempfile.TemporaryDirectory | None = None

    def __init__(
        self,
        _repo_dir: str,
        tmp_dir: tempfile.TemporaryDirectory,
        repo_full_name: str,
        installation_id: str = "",
        branch: str | None = None,
        token: str | None = None,
        repo: Any | None = None,
        git_repo: git.Repo | None = None,
    ):
        self._repo_dir = _repo_dir
        self.tmp_dir = tmp_dir
        self.repo_full_name = repo_full_name
        self.installation_id = installation_id
        self.branch = branch
        self.token = token
        self.repo = repo

    @classmethod
    def copy_from_cloned_repo(cls, cloned_repo: ClonedRepo, **kwargs):
        temp_dir = tempfile.TemporaryDirectory()
        new_dir = temp_dir.name + "/" + cloned_repo.repo_full_name.split("/")[1]
        print("Copying...")
        shutil.copytree(cloned_repo.repo_dir, new_dir)
        print("Done copying.")
        return cls(
            _repo_dir=new_dir,
            tmp_dir=temp_dir,
            repo_full_name=cloned_repo.repo_full_name,
            installation_id=cloned_repo.installation_id,
            branch=cloned_repo.branch,
            token=cloned_repo.token,
            repo=cloned_repo.repo,
            **kwargs,
        )

    def __del__(self):
        print(f"Dropping {self.tmp_dir.name}...")
        shutil.rmtree(self._repo_dir, ignore_errors=True)
        self.tmp_dir.cleanup()
        print("Done.")
        return True


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


def parse_collection_name(name: str) -> str:
    # Replace any non-alphanumeric characters with hyphens
    name = re.sub(r"[^\w-]", "--", name)
    # Ensure the name is between 3 and 63 characters and starts/ends with alphanumeric
    name = re.sub(r"^(-*\w{0,61}\w)-*$", r"\1", name[:63].ljust(3, "x"))
    return name

# set whether or not a pr is a draft, there is no way to do this using pygithub
def convert_pr_draft_field(pr: PullRequest, is_draft: bool = False):
    pr_id = pr.raw_data['node_id']
    # GraphQL mutation for marking a PR as ready for review
    mutation = """
    mutation MarkPRReady {
    markPullRequestReadyForReview(input: {pullRequestId: {pull_request_id}}) {
    pullRequest {
    id
    }
    }
    }
    """.replace("{pull_request_id}", "\""+pr_id+"\"")

    # GraphQL API URL
    url = 'https://api.github.com/graphql'

    # Headers
    headers={
        "Accept": "application/vnd.github+json",
        "X-Github-Api-Version": "2022-11-28",
        "Authorization": "Bearer " + os.environ["GITHUB_PAT"],
    }

    # Prepare the JSON payload
    json_data = {
        'query': mutation,
    }

    # Make the POST request
    response = requests.post(url, headers=headers, data=json.dumps(json_data))
    if response.status_code != 200:
        logger.error(f"Failed to convert PR to {'draft' if is_draft else 'open'}")
        return False
    return True


try:
    g = Github(os.environ.get("GITHUB_PAT"))
    CURRENT_USERNAME = g.get_user().login
except Exception:
    try:
        slug = get_app()["slug"]
        CURRENT_USERNAME = f"{slug}[bot]"
    except Exception:
        CURRENT_USERNAME = GITHUB_BOT_USERNAME

if __name__ == "__main__":
    # str1 = "a\nline1\nline2\nline3\nline4\nline5\nline6\ntest\n"
    # str2 = "a\nline1\nlineTwo\nline3\nline4\nline5\nlineSix\ntset\n"
    # print(get_hunks(str1, str2, 1))
    mocked_repo = MockClonedRepo.from_dir(
        "benchmark/data/repos/pulse-alp",
        repo_full_name="sweepai/sweep",
    )
    temp_repo = TemporarilyCopiedClonedRepo.copy_from_cloned_repo(mocked_repo)
    print(mocked_repo)
