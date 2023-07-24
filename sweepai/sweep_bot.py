from github import Github
from github.PullRequest import PullRequest
from github.PullRequestEvent import PullRequestEvent
from loguru import logger

from sweepai.handlers.create_pr import create_gha_pr
from sweepai.utils.config.client import SweepConfig

class SweepBot:
    def __init__(self, github_token: str, repo_full_name: str):
        self.github = Github(github_token)
        self.repo = self.github.get_repo(repo_full_name)

    def on_pr_merged(self, event: PullRequestEvent):
        pr: PullRequest = event.pull_request
        if pr.title == "Configure Sweep":
            create_gha_pr(self)