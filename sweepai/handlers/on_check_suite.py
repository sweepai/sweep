"""
This module is responsible for handling the check suite event, called from sweepai/api.py
"""
from contextlib import contextmanager
import io
import os
import re
import subprocess
from time import sleep
import zipfile

from loguru import logger
import requests

from github.Repository import Repository
from github.CommitStatus import CommitStatus
from sweepai.config.client import get_config_key_value
from sweepai.config.server import CIRCLE_CI_PAT, DOCKERFILE_CONFIG_LOCATION
from sweepai.dataclasses.check_status import CheckStatus
from sweepai.dataclasses.dockerfile_config import DockerfileConfig, load_dockerfile_configs_from_path
from sweepai.logn.cache import file_cache
from sweepai.utils.github_utils import ClonedRepo, get_token
from sweepai.utils.streamable_functions import streamable
from sweepai.utils.timer import Timer

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
<errors>
{error_content}
</errors>
Here are the logs:
<logs>
{cleaned_logs_str}
</logs>"""


@contextmanager
def change_dir(destination):
    prev_dir = os.getcwd()
    os.chdir(destination)
    try:
        yield
    finally:
        os.chdir(prev_dir)

@streamable
def get_failing_docker_logs(cloned_repo: ClonedRepo):
    """
    Input: ClonedRepo object
    Output:
    - logs, a string containing the logs of the failing docker container
    - image_name, a string containing the name of the docker image (for later cleanup)
    """
    # image name should be an input arg and cleaned up at the end
    if not DOCKERFILE_CONFIG_LOCATION:
        # this method should not be called if the dockerfile config is not present
        return "", ""
    dockerfile_configs = load_dockerfile_configs_from_path(DOCKERFILE_CONFIG_LOCATION)
    @streamable
    def run_dockerfile_config(dockerfile_config: DockerfileConfig, cloned_repo: ClonedRepo):
        image_name = dockerfile_config.image_name + "-" + str(hash(cloned_repo.repo_dir))[-8:]
        container_name = dockerfile_config.container_name + "-" + str(hash(cloned_repo.repo_dir))[-8:]
        dockerfile_path = dockerfile_config.dockerfile_path
        env_path = os.path.join(os.path.join(os.getcwd(), os.path.dirname(dockerfile_path)), ".env")
        env_exists = os.path.exists(env_path)
        dockerfile_path = os.path.join(os.getcwd(), dockerfile_path)
        logs = ""

        status: CheckStatus = {
            "message": "",
            "stdout": "",
            "succeeded": None,
            "status": "running",
            "llm_message": "",
            "container_name": container_name,
        }
        with Timer():
            try:
                with change_dir(cloned_repo.repo_dir):
                    # Build the Docker image
                    build_command = f"docker build -t {image_name} -f {dockerfile_path} --build-arg CODE_PATH=. ."
                    # Disable BuildKit to avoid issues with Dockerfile syntax
                    disable_buildkit_prefix = "DOCKER_BUILDKIT=0"
                    build_command = f"{disable_buildkit_prefix} {build_command}"
                    status["message"] = "Building Docker image..."
                    yield status
                    subprocess.run(build_command, shell=True, check=True, capture_output=True, text=True)
                    logger.info(f"Built Docker image {image_name}")
                    # Run the Docker container and remove it after it exits
                    if env_exists:
                        run_command = f"docker run --env-file {env_path} --name {container_name} {image_name} {dockerfile_config.command}"
                    else:
                        run_command = f"docker run --name {container_name} {image_name} {dockerfile_config.command}"
                    status["message"] = "Running Docker image..."
                    yield status
                    logger.info(f"Running Docker image {image_name}...")
                    with Timer():
                        # Use Popen to stream output
                        stdout = ""
                        with subprocess.Popen(run_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
                            for line in proc.stdout:
                                print(line, end='', flush=True)
                                stdout += line
                                status["stdout"] = stdout
                                yield status
                    status["message"] = f"Checks passed" if proc.returncode == 0 else f"Checks failed"
                    status["status"] = "success" if proc.returncode == 0 else "failure"
                    status["succeeded"] = proc.returncode == 0
                    yield status
                    with Timer():
                        # Remove the Docker container
                        remove_command = f"docker rm {container_name}"
                        status["message"] = "Removing Docker container..."
                        yield status
                        subprocess.run(remove_command, shell=True, check=True, capture_output=True, text=True)
                        if proc.returncode == 0:
                            logger.info(f"Docker container {container_name} exited successfully")
                            status["message"] = "Checks passed"
                            yield status
                            return "", image_name
                        else:
                            logger.error(f"Docker container {container_name} exited with error code {proc.returncode}")
                        logger.info(f"Removed Docker container {container_name}")
                        gha_formatted_prompt = gha_prompt.format(
                            command_line=dockerfile_config.command,
                            error_content=stdout,
                            cleaned_logs_str="",
                        )
                        status["llm_message"] = gha_formatted_prompt
                        status["message"] = "Checks failed"
                        yield status
                        return gha_formatted_prompt, image_name
            except subprocess.CalledProcessError as e:
                # TODO: handle this case
                logs = e.stdout + e.stderr
            gha_formatted_prompt = gha_prompt.format(
                command_line=dockerfile_config.command,
                error_content=logs,
                cleaned_logs_str="",
            )
            status["message"] = "Checks failed"
            status["succeeded"] = False
            status["stdout"] = logs
            status["llm_message"] = gha_formatted_prompt
            yield status
            return gha_formatted_prompt, image_name
    # run dockerfile configs in parallel
    docker_logs = ""
    image_names = []
    statuses = [{
        "message": "Queued",
        "stdout": "",
        "succeeded": None,
        "status": "pending",
        "llm_message": "",
        "container_name": dockerfile_config.container_name + "-" + str(hash(cloned_repo.repo_dir))[-8:],
    } for dockerfile_config in dockerfile_configs]
    for i, dockerfile_config in enumerate(dockerfile_configs):
        for status in run_dockerfile_config.stream(dockerfile_config, cloned_repo):
            statuses[i] = status
            yield statuses
        if status["succeeded"] == False:
            statuses[i+1:] = [{**status, "status": "cancelled", "message": "Check cancelled"} for status in statuses[i+1:]]
            yield statuses
            break # stop at the first failing docker container
    return docker_logs, image_names

def delete_docker_images(docker_image_names: str):
    for image_name in docker_image_names:
        delete_command = f"docker rmi {image_name}"
        try:
            subprocess.run(delete_command, shell=True, check=True)
            logger.info(f"Deleted Docker image: {image_name}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Error deleting Docker image: {image_name}")
            logger.warning(f"Error message: {str(e)}")


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
    # hacky workaround because circleci can have a setup that takes a long time, and we will report "success" because the setup has finished but the actual CI is still running
    logger.debug("Waiting for 60 seconds before polling for CircleCI status.")
    sleep(60)
    while True:
        commit = repo.get_commit(current_commit)
        status = commit.get_combined_status()
        # https://docs.github.com/en/rest/commits/statuses?apiVersion=2022-11-28#get-the-combined-status-for-a-specific-reference
        all_statuses: list[CommitStatus] = status.statuses
        # if all are success, break
        if all(status.state == "success" for status in all_statuses):
            failing_statuses = []
            logger.debug(f"Exiting polling for CircleCI as all statuses are success. Statuses were: {all_statuses}")
            break
        # if any of the statuses are failure, return those statuses
        failing_statuses = [status for status in all_statuses if status.state == "failure"]
        if failing_statuses:
            logger.debug(f"Exiting polling for CircleCI as some statuses are failing. Statuses were: {all_statuses}")
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
    # filter out statuses that are not allowed
    # this only executes if allowed_cicd_names is not None
    allowed_cicd_names = get_config_key_value(repo, "allowed_cicd_names")
    if allowed_cicd_names:
        failing_statuses = [status for status in failing_statuses if any(cicd_name in status.context.lower() for cicd_name in allowed_cicd_names)]
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