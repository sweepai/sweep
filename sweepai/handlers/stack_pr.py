from github.PullRequest import PullRequest

from sweepai.utils.github_utils import get_github_client


def stack_pr(
    request: str,
    pr_number: int,
    username: str,
    repo_full_name: str,
    installation_id: int,
    tracking_id: str,
):
    g, _token = get_github_client(installation_id=installation_id)
    repo = g.get_repo(repo_full_name)
    pr: PullRequest = repo.get_pull(pr_number)

    comment = pr.create_issue_comment(
        body=f"**Tracking ID:** {tracking_id}\n\n{request}"
    )

    return {"success": True}
