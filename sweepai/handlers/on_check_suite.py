import io
import os
import zipfile
import openai
import requests
from sweepai.core.gha_extraction import GHAExtractor

from sweepai.events import CheckRunCompleted

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

headers={
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {github_access_token}",
    "X-GitHub-Api-Version": "2022-11-28"
}

def retrieve_logs(repo_full_name: str, run_id: int) -> str:
    response = requests.get(f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs", headers=headers)

    logs_str = ""
    if response.status_code == 200:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        for file in zip_file.namelist():
            if "/" not in file:
                with zip_file.open(file) as f:
                    logs_str += f.read().decode("utf-8")
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
    logs = retrieve_logs(
        request.repository.full_name, 
        request.check_run.run_id
    )
    logs = clean_logs(logs)
    extractor = GHAExtractor()
    logs = extractor.gha_extract(logs)
    return logs
