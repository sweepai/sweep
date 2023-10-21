"""
This module is responsible for handling the check suite event, called from sweepai/api.py
"""
import io
import os
import zipfile

import openai
import requests

from sweepai.config.client import get_gha_enabled
from sweepai.core.entities import PRChangeRequest
from sweepai.core.gha_extraction import GHAExtractor
from sweepai.events import CheckRunCompleted
from sweepai.logn import logger
from sweepai.utils.github_utils import get_github_client, get_token

openai.api_key = os.environ.get("OPENAI_API_KEY")

log_message = """GitHub actions yielded the following error.

{error_logs}

Fix the code changed by the PR, don't modify the existing tests."""


def get_dirs(zipfile: zipfile.ZipFile):
    return [file for file in zipfile.namelist() if file.endswith("/") and "/" in file]


def get_files_in_dir(zipfile: zipfile.ZipFile, dir: str):
    return [
        file
        for file in zipfile.namelist()
        if file.startswith(dir) and not file.endswith("/")
    ]


def download_logs(repo_full_name: str, run_id: int, installation_id: int):
    token = get_token(installation_id)
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs",
        headers=headers,
    )

    logs_str = ""
    if response.status_code == 200:
        # this is the worst code I've ever written. I'm sorry.
        content = response.content
        zip_file = zipfile.ZipFile(io.BytesIO(content))
        for file in zip_file.namelist():
            if file.endswith(".txt"):
                with zip_file.open(file) as f:
                    logs = f.read().decode("utf-8")
                    last_line = logs.splitlines()[-1]
                    if "##[error]" in last_line:
                        logs_str += logs
    else:
        logger.info(response.text)
        logger.warning(f"Failed to download logs for run id: {run_id}")
    return logs_str


def clean_logs(logs_str: str):
    # Extraction process could be better
    MAX_LINES = 300
    log_list = logs_str.split("\n")
    truncated_logs = [log[log.find(" ") + 1 :] for log in log_list]
    patterns = [
        # for docker
        "Already exists",
        "Pulling fs layer",
        "Waiting",
        "Download complete",
        "Verifying Checksum",
        "Pull complete",
        # For github
        "remote: Counting objects",
        "remote: Compressing objects:",
        "Receiving objects:",
        "Resolving deltas:",
        "[command]/usr/bin/git ",
        "Download action repository",
        # For python
        "Collecting",
        "Downloading",
        "Installing",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        # For prettier
        "npm WARN EBADENGINE ",
        "npm WARN deprecated ",
        "prettier/prettier",
    ]
    cleaned_lines = [
        log.strip()
        for log in truncated_logs
        if not any(log.strip().startswith(pattern) for pattern in patterns)
    ]
    return "\n".join(cleaned_lines[: min(MAX_LINES, len(cleaned_lines))])


def extract_logs_from_comment(comment: str) -> str:
    if comment.count("```") < 2:
        return ""
    return comment[comment.find("```") + 3 : comment.rfind("```")]


def on_check_suite(request: CheckRunCompleted):
    logger.info(
        f"Received check run completed event for {request.repository.full_name}"
    )
    _, g = get_github_client(request.installation.id)
    repo = g.get_repo(request.repository.full_name)
    if not get_gha_enabled(repo):
        logger.info(
            f"Skipping github action for {request.repository.full_name} because it is"
            " not enabled"
        )
        return None
    pr = repo.get_pull(request.check_run.pull_requests[0].number)
    num_pr_commits = len(list(pr.get_commits()))
    if num_pr_commits > 20:
        logger.info(f"Skipping github action for PR with {num_pr_commits} commits")
        return None
    logger.info(f"Running github action for PR with {num_pr_commits} commits")
    logs = download_logs(
        request.repository.full_name, request.check_run.run_id, request.installation.id
    )
    if not logs:
        return None
    logs = clean_logs(logs)
    extractor = GHAExtractor(chat_logger=None)
    logger.info(f"Extracting logs from {request.repository.full_name}, logs: {logs}")
    problematic_logs = extractor.gha_extract(logs)
    if problematic_logs.count("\n") > 20:
        problematic_logs += (
            "\n\nThere are a lot of errors. This is likely due to a parsing issue"
            " or a missing import with the files changed in the PR."
        )
    comments = list(pr.get_issue_comments())
    if all([comment.user.login.startswith("sweep") for comment in comments[-4:]]):
        comment = pr.as_issue().create_comment(
            log_message.format(error_logs=problematic_logs)
            + "\n\nI'm getting the same errors 3 times in a row, so I will stop working"
            " on fixing this PR."
        )
        logger.warning("Skipping logs because it is duplicated")
        return None
    comment = pr.as_issue().create_comment(
        log_message.format(error_logs=problematic_logs)
    )
    pr_change_request = PRChangeRequest(
        params={
            "type": "github_action",
            "repo_full_name": request.repository.full_name,
            "repo_description": request.repository.description,
            "comment": problematic_logs,
            "pr_path": None,
            "pr_line_position": None,
            "username": request.sender.login,
            "installation_id": request.installation.id,
            "pr_number": request.check_run.pull_requests[0].number,
            "comment_id": comment.id,
        },
    )
    return pr_change_request
