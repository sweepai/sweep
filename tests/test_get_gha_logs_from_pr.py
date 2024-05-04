
import os
from sweepai.utils.ticket_rendering_utils import get_failing_gha_logs
from sweepai.utils.github_utils import get_github_client, get_installation_id


PR_ID = 3618
INSTALLATION_ID = os.environ.get("INSTALLATION_ID")
REPO_FULL_NAME = "sweepai/sweep"

installation_id = get_installation_id(REPO_FULL_NAME.split("/")[0])
print("Fetching access token...")
_token, g = get_github_client(installation_id)
print("Fetching repo...")
repo = g.get_repo(f"{REPO_FULL_NAME}")
pr = repo.get_pull(int(PR_ID))
runs = list(repo.get_workflow_runs(branch=pr.head.ref, head_sha=pr.head.sha))
failed_runs = [
    run for run in runs if run.conclusion == "failure"
]
import pdb; pdb.set_trace()
failed_gha_logs: list[str] = get_failing_gha_logs(
                            failed_runs,
                            INSTALLATION_ID,
                        )
import pdb; pdb.set_trace()


