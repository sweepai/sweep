import io
import os
import zipfile

import openai
import requests
from loguru import logger

from sweepai.core.gha_extraction import GHAExtractor
from sweepai.events import CheckRunCompleted
from sweepai.handlers.on_comment import on_comment
from sweepai.utils.config.client import SweepConfig, get_gha_enabled
from sweepai.utils.github_utils import get_github_client, get_token

openai.api_key = os.environ.get("OPENAI_API_KEY")

log_message = """GitHub actions yielded the following error:

{error_logs}"""

def download_logs(repo_full_name: str, run_id: int, installation_id: int):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {get_token(installation_id)}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    response = requests.get(f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs",
                            headers=headers)

    logs_str = ""
    if response.status_code == 200:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        for file in zip_file.namelist():
            if "/" not in file:
                with zip_file.open(file) as f:
                    logs_str += f.read().decode("utf-8")
    else:
        logger.warning(f"Failed to download logs for run id: {run_id}")
    return logs_str


def clean_logs(logs_str: str):
    log_list = logs_str.split("\n")
    truncated_logs = [log[log.find(" ") + 1:] for log in log_list]
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
        "Resolving deltas:"
    ]
    return "\n".join([log.strip() for log in truncated_logs if not any(pattern in log for pattern in patterns)])


def on_check_suite(request: CheckRunCompleted):
    logger.info(f"Received check run completed event for {request.repository.full_name}")
    g = get_github_client(request.installation.id)
    repo = g.get_repo(request.repository.full_name)
    if not get_gha_enabled(repo):
        logger.info(f"Skipping github action for {request.repository.full_name} because it is not enabled")
        return None
    pr = repo.get_pull(request.check_run.pull_requests[0].number)
    num_pr_commits = len(list(pr.get_commits()))
    if num_pr_commits > 20:
        logger.info(f"Skipping github action for PR with {num_pr_commits} commits")
        return None
    logger.info(f"Running github action for PR with {num_pr_commits} commits")
    logs = download_logs(
        request.repository.full_name,
        request.check_run.run_id,
        request.installation.id
    )
    if not logs:
        return None
    logs = clean_logs(logs)
    extractor = GHAExtractor()
    logger.info(f"Extracting logs from {request.repository.full_name}, logs: {logs}")
    problematic_logs = extractor.gha_extract(logs)
    if problematic_logs.count("\n") > 15:
        problematic_logs += "\n\nThere are a lot of errors. This is likely a larger issue with the PR and not a small linting/type-checking issue."
    comments = list(pr.get_issue_comments())
    if len(comments) >= 2 and problematic_logs == comments[-1].body and comments[-2].body == comments[-1].body:
        comment = pr.as_issue().create_comment(problematic_logs.format(error_logs=problematic_logs) + "\n\nI'm getting the same errors 3 times in a row, so I will stop working on fixing this PR.")
        logger.warning("Skipping logs because it is duplicated")
        raise Exception("Duplicate error logs")
    comment = pr.as_issue().create_comment(problematic_logs.format(error_logs=problematic_logs))
    on_comment(
        repo_full_name=request.repository.full_name,
        repo_description=request.repository.description,
        comment=problematic_logs,
        pr_path=None,
        pr_line_position=None,
        username=request.sender.login,
        installation_id=request.installation.id,
        pr_number=request.check_run.pull_requests[0].number,
        comment_id=comment.id,
        repo=repo,
    )
    return {"success": True}

