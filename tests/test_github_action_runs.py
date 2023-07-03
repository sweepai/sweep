import os
import requests

headers={
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {os.environ.get('GITHUB_PAT')}",
    "X-GitHub-Api-Version": "2022-11-28"
}

def get_run_id(repo_full_name: str, check_run_id: int):
    response = requests.get(f"https://api.github.com/repos/{repo_full_name}/check-runs/{check_run_id}", headers=headers)
    check_run_html_url = response.json()["html_url"]
    # format is like https://github.com/ORG/REPO_NAME/actions/runs/RUN_ID/jobs/JOB_ID
    run_id = check_run_html_url.split("/")[-3]
    return run_id

def download_logs(repo_full_name: str, run_id: int):
    response = requests.get(f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs", headers=headers)

    if response.status_code == 200:
        with open("logs.zip", "wb") as f:
            f.write(response.content)

if __name__ == "__main__":
    repo_full_name = "sagewhocodes/ivy"
    run_id = 14727682439
    download_logs(repo_full_name, get_run_id(repo_full_name, run_id))
