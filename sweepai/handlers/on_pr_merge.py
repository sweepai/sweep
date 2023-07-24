from .create_pr import create_pr
from ..models import PullRequest, FileChangeRequest
from ..main import sweep_bot

def on_pr_merge(merged_pr: PullRequest):
    if merged_pr.title == 'config PR':
        file_change_request = FileChangeRequest(
            file_path='sweep.yaml',
            content='gha_enabled: True'
        )
        create_pr(
            file_change_requests=[file_change_request],
            pull_request=merged_pr,
            sweep_bot=sweep_bot,
            username=merged_pr.author,
            installation_id=merged_pr.installation_id
        )