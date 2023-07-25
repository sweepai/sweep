from sweepai.events import GithubEvent
from sweepai.handlers.create_issue import create_issue

def on_pull_request_merged(event: GithubEvent):
    if event.data['pull_request']['title'] == 'Enable Github Actions' and event.data['action'] == 'closed':
        create_issue(event.repo, 'Sweep: Set up linters using GHA', 'Please set up the appropriate linters using GitHub Actions based on the primary language of the repository.')