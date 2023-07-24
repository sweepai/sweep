import io
import os
import zipfile

import openai
import requests
from github import PullRequestEvent
from loguru import logger
from sweepai.handlers.create_pr import enable_gha

from sweepai.core.gha_extraction import GHAExtractor
from sweepai.events import CheckRunCompleted
from sweepai.utils.config.client import SweepConfig, get_gha_enabled
from sweepai.utils.github_utils import get_github_client, get_token

openai.api_key = os.environ.get("OPENAI_API_KEY")


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
    ...
    return logs


def on_pull_request_closed(request: PullRequestEvent):
    if request.action == "closed" and request.pull_request.merged:
        g = get_github_client(request.installation.id)
        repo = g.get_repo(request.repository.full_name)
        sweep_bot = SweepBot(repo, request.installation.id)
        enable_gha(sweep_bot, repo)
    if not get_gha_enabled(repo):
        return None
    pr = repo.get_pull(request.check_run.pull_requests[0].number)
    num_pr_commits = len(list(pr.get_commits()))
    if num_pr_commits > 6:
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
    logs = extractor.gha_extract(logs)
    return logs
