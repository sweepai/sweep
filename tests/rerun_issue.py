import html
import time
import traceback  # Import the traceback module

import requests
import typer
from github import Github

from sweepai.events import Account, Installation, IssueRequest
from sweepai.utils.github_utils import get_github_client, get_installation_id

def wait_for_server(host: str):
    for i in range(120):
        try:
            response = requests.get(host)
            if response.status_code == 200:
                break
        except:
            print(
                f"Waited for server to start ({i+1}s)"
                + ("." * (i % 4) + " " * (4 - (i % 4))),
                end="\r",
            )
            traceback.print_exc()  # Print the traceback when an exception occurs
            time.sleep(1)
            continue

def fetch_issue_request(issue_url: str, __version__: str = "0"):
    (
        protocol_name,
        _,
        _base_url,
        org_name,
        repo_name,
        _issues,
        issue_number,
    ) = issue_url.split("/")
    print("Fetching installation ID...")
    installation_id = get_installation_id(org_name)
    print("Fetching access token...")
    _token, g = get_github_client(installation_id)
    g: Github = g
    print("Fetching repo...")
    issue = g.get_repo(f"{org_name}/{repo_name}").get_issue(int(issue_number))

    issue_request = IssueRequest(
        action="labeled",
        issue=IssueRequest.Issue(
            title=issue.title,
            number=int(issue_number),
            html_url=issue_url,
            user=IssueRequest.Issue.User(
                login=issue.user.login,
                type="User",
            ),
            body=issue.body,
            labels=[
                IssueRequest.Issue.Label(
                    name="sweep",
                ),
            ],
            assignees=None,
            pull_request=None,
        ),
        repository=IssueRequest.Issue.Repository(
            full_name=issue.repository.full_name,
            description=issue.repository.description,
        ),
        assignee=IssueRequest.Issue.Assignee(login=issue.user.login),
        installation=Installation(
            id=installation_id,
            account=Account(
                id=issue.user.id,
                login=issue.user.login,
                type="User",
            ),
        ),
        sender=IssueRequest.Issue.User(
            login=issue.user.login,
            type="User",
        ),
    )

    return issue_request

def main(
    issue_url: str,
    host: str = "http://127.0.0.1:8080",
    better_stack_prefix: str = "https://logs.betterstack.com/team/199101/tail?rf=now-30m&q=metadata.issue_url%3A",
):
    issue_url = issue_url or typer.prompt("Issue URL")
    print(f"Fetching issue metdata...")
    issue_request = fetch_issue_request(issue_url)
    wait_for_server(host)
    print(f"Sending request...")
    response = requests.post(
        host,
        json=issue_request.dict(),
        headers={"X-GitHub-Event": "issues"},
    )
    print(response)
    better_stack_link = f"{better_stack_prefix}{html.escape(issue_url)}"
    print(f"Track the logs at the following link:\n\n{better_stack_link}")

if __name__ == "__main__":
    typer.run(main)
