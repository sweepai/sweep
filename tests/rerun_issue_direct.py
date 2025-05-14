import hashlib
import hmac
import html
import json
import multiprocessing

import typer
from fastapi.testclient import TestClient

from sweepai.api import app
from sweepai.config.server import WEBHOOK_SECRET
from sweepai.web.event_utils import fetch_issue_request


def send_request(issue_request):
    with TestClient(app) as client:
        response = client.post(
            "/", json=issue_request.dict(), headers={"X-GitHub-Event": "issues"}
        )
        print(response)  # or return response, depending on your needs


def test_issue_url(
    issue_url: str,
    better_stack_prefix: str = "https://logs.betterstack.com/team/199101/tail?rf=now-30m&q=metadata.issue_url%3A",
    debug: bool = True,
):
    issue_url: str = issue_url or typer.prompt("Issue URL")
    print("Fetching issue metadata...")
    (
        _,
        _,
        _,
        org_name,
        repo_name,
        _,
        issue_number,
    ) = issue_url.split("/")
    issue_request = fetch_issue_request(
        org_name=org_name,
        repo_name=repo_name,
        issue_number=issue_number,
        issue_url=issue_url
    )
    print("Sending request...")

    # assert WEBHOOK_SECRET, "WEBHOOK_SECRET not set"
    sha = ""
    if WEBHOOK_SECRET:
        sha = hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            msg=json.dumps(issue_request.model_dump()).encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
    if debug:
        client = TestClient(app)
        response = client.post(
            "/", 
            json=issue_request.dict(),
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": f"sha256={sha}"
            }
        )
        print(response)
    else:
        request_process = multiprocessing.Process(
            target=send_request, args=(issue_request,)
        )
        request_process.start()

        request_process.join(timeout=150)

        if request_process.is_alive():
            print("Terminating the process...")
            request_process.terminate()
            request_process.join()  # Ensure process has terminated before proceeding

    better_stack_link = f"{better_stack_prefix}{html.escape(issue_url)}"


if __name__ == "__main__":
    typer.run(test_issue_url)
