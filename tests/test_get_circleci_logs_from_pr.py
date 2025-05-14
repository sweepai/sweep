
import os

from loguru import logger
import requests
from sweepai.config.server import CIRCLE_CI_PAT
from sweepai.utils.github_utils import get_github_client, get_installation_id
from sweepai.utils.ticket_rendering_utils import remove_ansi_tags


PR_ID = os.environ.get("PR_ID")
INSTALLATION_ID = os.environ.get("INSTALLATION_ID")
REPO_FULL_NAME = os.environ.get("REPO_FULL_NAME")

installation_id = get_installation_id(REPO_FULL_NAME.split("/")[0])
print("Fetching access token...")
_token, g = get_github_client(installation_id)
print("Fetching repo...")
repo = g.get_repo(f"{REPO_FULL_NAME}")
pr = repo.get_pull(int(PR_ID))
commits = pr.get_commits()

def get_circleci_job_details(job_number, project_slug, vcs_type='github'):
    headers = {'Circle-Token': CIRCLE_CI_PAT}
    url = f"https://circleci.com/api/v1.1/project/{vcs_type}/{project_slug}/{job_number}"
    response = requests.get(url, headers=headers)
    return response.json()

# take a commit and return all failing logs as a list
def get_failing_circleci_logs(circleci_run_url: str):
    if not CIRCLE_CI_PAT:
        logger.warning("CIRCLE_CI_APIKEY not set")
        return []
    headers = {'Circle-Token': CIRCLE_CI_PAT}
    job_number = circleci_run_url.split("/")[-1]
    project_slug = REPO_FULL_NAME
    circleci_run_details = get_circleci_job_details(job_number, project_slug)

    steps = circleci_run_details['steps']
    failing_steps = []
    failed_commands_and_logs: list[tuple[str, str, str]] = []
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
                failed_commands_and_logs.append((command, error_message, log_message))
    for command, error, log in failed_commands_and_logs:
        print(f"Failed Command: {command}")
        print(f"Error: {error}")
        print("Logs:")
        print(log)
        print("---")
    return failed_commands_and_logs

for commit in commits:
    # Get the commit status
    status = commit.get_combined_status()

    # Check if the status context contains CircleCI runs
    for status_detail in status.statuses:
        if 'circleci' in status_detail.context.lower():
            # CircleCI run detected
            print(f"CircleCI run found for commit: {commit.sha}")
            print(f"CircleCI run URL: {status_detail.target_url}")
            get_failing_circleci_logs(circleci_run_url=status_detail.target_url)
