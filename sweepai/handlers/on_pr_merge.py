from sweepai.handlers.create_pr import create_pr
from sweepai.bot import SweepBot
from github.PullRequest import PullRequest

def on_pr_merge(sweep_bot: SweepBot, pr: PullRequest):
    if pr.title == "Configure Sweep":
        create_pr(sweep_bot)

# Register the handler
SweepBot.register_handler("pull_request.closed", on_pr_merge)