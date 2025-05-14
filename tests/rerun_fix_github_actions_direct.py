import typer

from sweepai.handlers.on_failing_github_actions import on_failing_github_actions
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import get_github_client, get_installation_id


def test_issue_url(
    pr_url: str,
):
    pr_url = pr_url or typer.prompt("PR URL")
    print("Fetching PR metadata...")
    (
        _,
        _,
        _,
        org_name,
        repo_name,
        _,
        pr_number,
    ) = pr_url.split("/")

    installation_id = get_installation_id(org_name)
    _token, g = get_github_client(installation_id)
    repo = g.get_repo(f"{org_name}/{repo_name}")
    pr = repo.get_pull(int(pr_number))

    body = pr.body
    if "fixes #" in body.lower():
        issue_number = body.lower().split("fixes #")[1].split(".")[0]
        issue = repo.get_issue(int(issue_number))
        problem_statement = issue.title + "\n" + issue.body
    else:
        problem_statement = pr.title + "\n" + pr.body

    on_failing_github_actions(
        problem_statement=problem_statement,
        repo=repo,
        username=repo.owner.login,
        pull_request=pr,
        user_token=_token,
        installation_id=installation_id,
        chat_logger=ChatLogger({"username": "on_failing_github_actions"}),
    )


if __name__ == "__main__":
    try:
        typer.run(test_issue_url)
    except Exception:
        import pdb
        pdb.post_mortem()
        raise
