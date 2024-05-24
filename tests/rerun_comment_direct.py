
from github import Github
import typer
from fastapi.testclient import TestClient

from sweepai.api import app
from sweepai.handlers.on_comment import on_comment
from sweepai.utils.github_utils import get_github_client, get_installation_id


def send_request(issue_request):
    with TestClient(app) as client:
        response = client.post(
            "/", json=issue_request.dict(), headers={"X-GitHub-Event": "issue_comment"}
        )
        print(response)  # or return response, depending on your needs


def pull_request_url(
    comment_url: str,
    better_stack_prefix: str = "https://logs.betterstack.com/team/199101/tail?rf=now-30m&q=metadata.issue_url%3A",
    debug: bool = True,
):
    
    print("Fetching issue metadata...")
    is_review_comment = False
    if "issuecomment" in comment_url:
        (
            _,
            _,
            _,
            org_name,
            repo_name,
            _,
            pr_number_and_comment_id,
        ) = comment_url.split("/")
        pr_number, comment_id = pr_number_and_comment_id.split("#issuecomment-")
    else:
        is_review_comment = True
        (
            _,
            _,
            _,
            org_name,
            repo_name,
            _,
            pr_number,
            files_and_comment_id,
        ) = comment_url.split("/")
        comment_id = files_and_comment_id.split("#")[1][1:] # Remove "r" from the comment ID

    installation_id = get_installation_id(org_name)
    print("Fetching access token...")
    _token, g = get_github_client(installation_id)
    g: Github = g
    print("Fetching repo...")
    repo = g.get_repo(f"{org_name}/{repo_name}")
    pr_number = int(pr_number)
    pr = repo.get_pull(pr_number)
    comment_object = None
    if is_review_comment:
        for review_comment in pr.get_review_comments():
            if review_comment.html_url.endswith(f"{comment_id}"):
                comment_object = review_comment
                break
        on_comment(
            username=comment_object.user.login,
            repo_full_name=f"{org_name}/{repo_name}",
            repo_description=repo.description,
            comment=comment_object.body,
            pr_path=comment_object.path,
            pr_line_position=comment_object.position,
            installation_id=installation_id,
            pr_number=pr_number,
            comment_id=int(comment_id),
            chat_logger=None
        )
    else:
        for comment in pr.get_issue_comments():
            if comment.html_url.endswith(f"{comment_id}"):
                comment_object = comment
                break
        on_comment(
            username=comment_object.user.login,
            repo_full_name=f"{org_name}/{repo_name}",
            repo_description=repo.description,
            comment=comment_object.body,
            pr_path=None,
            pr_line_position=None,
            installation_id=installation_id,
            pr_number=pr_number,
            comment_id=int(comment_id),
            chat_logger=None
        )


if __name__ == "__main__":
    typer.run(pull_request_url)