import io
import os
import zipfile
import requests
from loguru import logger


def download_logs(repo_full_name: str, run_id: int):
    token = os.environ.get("GITHUB_PAT")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    response = requests.get(f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs",
                            headers=headers)

    logs_str = ""
    if response.status_code == 200:
        # this is the worst code I've ever written. I'm sorry.
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        files = [file[file.find("/") + 1:] for file in zip_file.namelist() if "/" in file and not file.endswith("/")]
        numbers = [int(file[:file.find("_")]) for file in files]
        for i in range(1, 100):
            if i not in numbers:
                break
        i -= 1
        target_file = ""
        for file in zip_file.namelist():
            if "/" in file and file[file.find("/") + 1: file.rfind("_")] == str(i):
                target_file = file
                break
        else:
            raise ValueError("No file found")
        with zip_file.open(target_file) as f:
            logs_str += f.read().decode("utf-8")
    else:
        logger.info(response.text)
        logger.warning(f"Failed to download logs for run id: {run_id}")
    return logs_str


def clean_logs(logs_str: str):
    # Extraction process could be better
    MAX_LINES = 300
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
        "prettier/prettier"

    ]
    cleaned_lines = [log.strip() for log in truncated_logs if not any(log.strip().startswith(pattern) for pattern in patterns)]
    return "\n".join(cleaned_lines[:min(MAX_LINES, len(cleaned_lines))])

if __name__ == "__main__":
    run_id = 5753755655
    print(clean_logs(download_logs("sweepai/sweep", run_id)))