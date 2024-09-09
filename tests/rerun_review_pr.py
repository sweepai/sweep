import hashlib
import hmac
import html
import json

import typer
from fastapi.testclient import TestClient

from sweepai.api import app
from sweepai.config.server import WEBHOOK_SECRET
from sweepai.utils.github_utils import get_github_client, get_installation_id, get_installation


def fetch_review_pr_request(issue_url: str, __version__: str = "0"):
    (
        protocol_name,
        _,
        _base_url,
        org_name,
        repo_name,
        _issues,
        pr_number,
    ) = issue_url.split("/")
    print("Fetching installation ID...")
    installation_id = get_installation_id(org_name)
    installation = get_installation(org_name)
    print("Fetching access token...")
    _token, g = get_github_client(installation_id)
    print("Fetching repo...")
    try:
        org = g.get_organization(org_name)
    except Exception:
        org = g.get_user(org_name)
    repo = g.get_repo(f"{org_name}/{repo_name}")
    pr = repo.get_pull(int(pr_number))

    review_pr_request = {
        "action": "opened",
        "number": int(pr_number),
        "pull_request": pr.raw_data,
        "repository": repo.raw_data,
        "organization": org.raw_data,
        "installation": installation
    }
    return review_pr_request


def send_request(issue_request):
    with TestClient(app) as client:
        response = client.post(
            "/", json=issue_request.dict(), headers={"X-GitHub-Event": "issues"}
        )
        print(response)  # or return response, depending on your needs


def review_pr(
    pr_url: str,
    better_stack_prefix: str = "https://logs.betterstack.com/team/199101/tail?rf=now-30m&q=metadata.issue_url%3A",
    debug: bool = True,
):
    pr_url: str = pr_url or typer.prompt("PR URL")
    print("Fetching issue metadata...")
    request = fetch_review_pr_request(pr_url)
    print("Sending request...")

    client = TestClient(app)
    sha = ""
    if WEBHOOK_SECRET:
        sha = hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            msg=json.dumps(request).encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
    response = client.post(
        "/",
        json=request,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": f"sha256={sha}"
        }
    )
    print(response)


    better_stack_link = f"{better_stack_prefix}{html.escape(pr_url)}"

# NOTE CURRENTLY THIS SCRIPT DOES NOT IGNORE RESOLVED COMMENTS
if __name__ == "__main__":
    typer.run(review_pr)
