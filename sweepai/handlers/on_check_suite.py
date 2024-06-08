"""
This module is responsible for handling the check suite event, called from sweepai/api.py
"""
import io
import re
from time import sleep
import zipfile

from loguru import logger
import requests

from github.Repository import Repository
from github.CommitStatus import CommitStatus
from sweepai.config.server import CIRCLE_CI_PAT
from sweepai.logn.cache import file_cache
from sweepai.utils.github_utils import get_token

MAX_LINES = 500
LINES_TO_KEEP = 100
CIRCLECI_SLEEP_DURATION_SECONDS = 15

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

def remove_ansi_tags(logs: str) -> str:
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', "", logs, flags=re.MULTILINE)

@file_cache()
def download_logs(repo_full_name: str, run_id: int, installation_id: int, get_errors_only=True):
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
                    elif not get_errors_only: # get all logs
                        logs_str += logs
    return logs_str

gha_prompt = """\
The below command yielded the following errors:
<command>
{command_line}
</command>
{error_content}
Here are the logs:
<logs>
{cleaned_logs_str}
</logs>"""


def clean_gh_logs(logs_str: str):
    # Extraction process could be better
    log_list = logs_str.split("\n")
    truncated_logs = [log[log.find(" ") + 1 :] for log in log_list]
    logs_str = "\n".join(truncated_logs)
    # extract the group and delete everything between group and endgroup
    gha_pattern = r"##\[group\](.*?)##\[endgroup\](.*?)(##\[error\].*)"
    match = re.search(gha_pattern, logs_str, re.DOTALL)
    if not match:
        return "\n".join(logs_str.split("\n")[:MAX_LINES])
    command_line = match.group(1).strip()
    log_content = match.group(2).strip()
    error_line = match.group(3).strip() # can be super long
    return clean_cicd_logs(
        command=command_line,
        error=error_line,
        logs=log_content,
    )

def clean_cicd_logs(command: str, error: str, logs: str):
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
        for log in logs.split("\n")
        if not any(log.strip().startswith(pattern) for pattern in patterns)
    ]
    if len(cleaned_logs) > MAX_LINES:
        # return the first LINES_TO_KEEP and the last LINES_TO_KEEP
        cleaned_logs = cleaned_logs[:LINES_TO_KEEP] + ["..."] + cleaned_logs[-LINES_TO_KEEP:]
    cleaned_logs_str = "\n".join(cleaned_logs)
    error_content = ""
    if len(error) < 200000:
        error_content = f"""<errors>
{error}
</errors>"""
    cleaned_response = gha_prompt.format(
        command_line=command,
        error_content=error_content,
        cleaned_logs_str=cleaned_logs_str,
    )
    return cleaned_response

def get_circleci_job_details(job_number, project_slug, vcs_type='github'):
    # project_slug is the repo full name
    headers = {'Circle-Token': CIRCLE_CI_PAT}
    url = f"https://circleci.com/api/v1.1/project/{vcs_type}/{project_slug}/{job_number}"
    response = requests.get(url, headers=headers)
    return response.json()

# take a commit and return all failing logs as a list
def get_failing_circleci_log_from_url(circleci_run_url: str, repo_full_name: str):
    if not CIRCLE_CI_PAT:
        logger.warning("CIRCLE_CI_APIKEY not set")
        return []
    headers = {'Circle-Token': CIRCLE_CI_PAT}
    job_number = circleci_run_url.split("/")[-1]
    circleci_run_details = get_circleci_job_details(job_number, repo_full_name)
    steps = circleci_run_details['steps']
    failing_steps = []
    failed_commands_and_logs = ""
    for step in steps:
        if step['actions'][0]['exit_code'] != 0:
            failing_steps.append(step)
    for step in failing_steps:
        actions = step['actions']
        for action in actions:
            if action.get("status") != "failed":
                continue
            if 'output_url' in action:
                log_url = action['output_url']
                log_response = requests.get(log_url, headers=headers)
                log_response = log_response.json()
                # these might return in a different order; watch out
                log_message = log_response[0]["message"] if len(log_response) > 0 else ""
                error_message = log_response[1].get("message", "") if len(log_response) > 1 else ""
                log_message = remove_ansi_tags(log_message)
                error_message = remove_ansi_tags(error_message)
                command = action.get("bash_command", "No command found.") # seems like this is the only command
                circle_ci_failing_logs = clean_cicd_logs(
                    command=command,
                    error=error_message,
                    logs=log_message,
                )
                if circle_ci_failing_logs:
                    failed_commands_and_logs += circle_ci_failing_logs + "\n"
    return failed_commands_and_logs

def get_failing_circleci_logs(
    repo: Repository,
    current_commit: str,
):
    # get the pygithub commit object
    all_logs = ""
    failing_statuses = []
    total_poll_attempts = 0
    while True:
        commit = repo.get_commit(current_commit)
        status = commit.get_combined_status()
        # https://docs.github.com/en/rest/commits/statuses?apiVersion=2022-11-28#get-the-combined-status-for-a-specific-reference
        all_statuses: list[CommitStatus] = status.statuses
        # if all are success, break
        if all(status.state == "success" for status in all_statuses):
            failing_statuses = []
            break
        # if any of the statuses are failure, return those statuses
        failing_statuses = [status for status in all_statuses if status.state == "failure"]
        if failing_statuses:
            break
        # if any of the statuses are pending, sleep and try again
        if any(status.state == "pending" for status in all_statuses):
            if total_poll_attempts * CIRCLECI_SLEEP_DURATION_SECONDS // 60 >= 60:
                logger.debug("Polling for CircleCI has taken too long, giving up.")
                break
            # wait between check attempts
            total_poll_attempts += 1
            logger.debug(f"Polling to see if CircleCI has finished... {total_poll_attempts}.")
            sleep(CIRCLECI_SLEEP_DURATION_SECONDS)
            continue
    # done polling
    for status_detail in failing_statuses:
        # CircleCI run detected
        if 'circleci' in status_detail.context.lower():
            failing_circle_ci_log = get_failing_circleci_log_from_url(
                circleci_run_url=status_detail.target_url,
                repo_full_name=repo.full_name
            ) # may be empty string
            if failing_circle_ci_log:
                all_logs += failing_circle_ci_log + "\n"
    return all_logs