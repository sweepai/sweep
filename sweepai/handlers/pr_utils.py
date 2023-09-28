from github import GithubException
from sweepai.config.server import GITHUB_LABEL_NAME
from sweepai.core.entities import SweepContext
from sweepai.handlers.create_pr import create_pr_changes
from sweepai.utils.github_utils import get_github_client

def build_context(username, issue_url, use_faster_model, is_paying_user, repo, token):
    sweep_context = SweepContext.create(
        username=username,
        issue_url=issue_url,
        use_faster_model=use_faster_model,
        is_paying_user=is_paying_user,
        repo=repo,
        token=token,
    )
    return sweep_context

def generate_pr_changes(file_change_requests, pull_request, sweep_bot, username, installation_id, issue_number, chat_logger):
    generator = create_pr_changes(
        file_change_requests,
        pull_request,
        sweep_bot,
        username,
        installation_id,
        issue_number,
        chat_logger=chat_logger,
    )
    return generator

def create_pull_request(repo, pr_changes, is_draft, issue_number):
    try:
        pr = repo.create_pull(
            title=pr_changes.title,
            body=pr_changes.body,
            head=pr_changes.pr_head,
            base=SweepConfig.get_branch(repo),
            draft=is_draft,
        )
    except GithubException as e:
        is_draft = False
        pr = repo.create_pull(
            title=pr_changes.title,
            body=pr_changes.body,
            head=pr_changes.pr_head,
            base=SweepConfig.get_branch(repo),
            draft=is_draft,
        )
    pr.add_to_labels(GITHUB_LABEL_NAME)
    return pr
