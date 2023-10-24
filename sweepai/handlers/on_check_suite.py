"""
This module is responsible for handling the check suite event, called from sweepai/api.py
"""
import io
import os
import re
import time
import zipfile

import openai
import requests

from sweepai.config.client import get_gha_enabled
from sweepai.core.entities import PRChangeRequest
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
        content = response.content
        zip_file = zipfile.ZipFile(io.BytesIO(content))
        for file in zip_file.namelist():
            if file.endswith(".txt"):
                with zip_file.open(file) as f:
                    logs = f.read().decode("utf-8")
                    last_line = logs.splitlines()[-1]
                    if "##[error]" in last_line:
                        logs_str += logs
    return logs_str


def clean_logs(logs_str: str):
    # Extraction process could be better
    MAX_LINES = 50
    log_list = logs_str.split("\n")
    truncated_logs = [log[log.find(" ") + 1 :] for log in log_list]
    logs_str = "\n".join(truncated_logs)
    # extract the group and delete everything between group and endgroup
    gha_pattern = r'##\[group\](.*?)##\[endgroup\](.*?)(##\[error\].*)'
    match = re.search(gha_pattern, logs_str, re.DOTALL)

    # Extract the matched groups
    if not match:
        return ""
    group_start = match.group(1).strip()
    command_line = group_start.split("\n")[0]
    log_content = match.group(2).strip()
    error_line = match.group(3).strip()

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
    cleaned_logs = [
        log.strip()
        for log in log_content.split("\n")
        if not any(log.strip().startswith(pattern) for pattern in patterns)
    ]
    if len(cleaned_logs) > MAX_LINES:
        return ""
    cleaned_logs_str = "\n".join(cleaned_logs)
    cleaned_response = f"""\
The command:
{command_line}
yielded the following error:
{error_line}

Here are the logs:
{cleaned_logs_str}"""
    response_for_user = f"""\
The command:
`{command_line}`
yielded the following error:
`{error_line}`
Here are the logs:
```
{cleaned_logs_str}
```"""
    return cleaned_response, response_for_user

def on_check_suite(request: CheckRunCompleted):
    pr_number = request.check_run.pull_requests[0].number
    repo_name = request.repository.full_name
    _, g = get_github_client(request.installation.id)
    repo = g.get_repo(repo_name)
    if not get_gha_enabled(repo):
        return None
    pr = repo.get_pull(pr_number)
    # check if the PR was created in the last 15 minutes
    if (time.time() - pr.created_at.timestamp()) > 900:
        return None
    issue_comments = pr.get_issue_comments()
    for comment in issue_comments:
        if "The command" in comment.body:
            return None
    logs = download_logs(
        request.repository.full_name, request.check_run.run_id, request.installation.id
    )
    if not logs:
        return None
    logs, user_message = clean_logs(logs)
    comment = pr.as_issue().create_comment(user_message)
    pr_change_request = PRChangeRequest(
        params={
            "type": "github_action",
            "repo_full_name": request.repository.full_name,
            "repo_description": request.repository.description,
            "comment": logs,
            "pr_path": None,
            "pr_line_position": None,
            "username": request.sender.login,
            "installation_id": request.installation.id,
            "pr_number": request.check_run.pull_requests[0].number,
            "comment_id": comment.id,
        },
    )
    return pr_change_request
