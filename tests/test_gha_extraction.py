from sweepai.config.server import INSTALLATION_ID
from sweepai.handlers.on_check_suite import clean_gh_logs, download_logs


def test_clean_gh_logs(run_id: int, installation_id: int, repo_full_name: str):
    logs = download_logs(
            repo_full_name=repo_full_name,
            run_id=run_id,
            installation_id=installation_id
        )
    if not logs:
        return None
    logs = clean_gh_logs(logs)
    return logs

RUN_ID = 8576903108
REPO_FULL_NAME = "sweepai/sweep"

logs = test_clean_gh_logs(RUN_ID, INSTALLATION_ID, REPO_FULL_NAME)