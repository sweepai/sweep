import io
import os
import zipfile
import requests

from sweepai.core.gha_extraction import GHAExtractor

headers={
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {os.environ.get('GITHUB_PAT')}",
    "X-GitHub-Api-Version": "2022-11-28"
}

def get_run_id(repo_full_name: str, check_run_id: int):
    response = requests.get(f"https://api.github.com/repos/{repo_full_name}/check-runs/{check_run_id}", headers=headers)
    obj = response.json()
    succeeded = obj["conclusion"] == "success"
    check_run_html_url = obj["html_url"]
    # format is like https://github.com/ORG/REPO_NAME/actions/runs/RUN_ID/jobs/JOB_ID
    run_id = check_run_html_url.split("/")[-3]
    return run_id

def download_logs(repo_full_name: str, run_id: int):
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


if __name__ == "__main__":
    repo_full_name = "sagewhocodes/ivy"
    run_id = 14727682439
    raw_logs = download_logs(repo_full_name, get_run_id(repo_full_name, run_id))
    extractor = GHAExtractor()
    logs = extractor.gha_extract(clean_logs(raw_logs))
    print(logs)
