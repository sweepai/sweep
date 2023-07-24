import modal
import openai
from loguru import logger
from github.Repository import Repository
from sweepai.core.sweep_bot import SweepBot, MaxTokensExceeded
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.event_logger import posthog

def create_gha_pr(sweep_bot: SweepBot):
    branch_name = sweep_bot.create_branch("gha-setup")
    sweep_bot.repo.create_file(
        'sweep.yaml',
        'Enable GitHub Actions',
        'gha_enabled: True',
        branch=branch_name
    )
    pr_title = "Enable GitHub Actions"
    pr_description = "This PR enables GitHub Actions for this repository."
    pr = sweep_bot.repo.create_pull(
        title=pr_title,
        body=pr_description,
        head=branch_name,
        base=SweepConfig.get_branch(sweep_bot.repo),
    )
    pr.add_to_labels(GITHUB_LABEL_NAME)
