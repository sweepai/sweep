import sys
import traceback

from sweepai.api import global_threads
from sweepai.handlers.review_pr import review_pr
from sweepai.utils.github_utils import get_github_client, get_installation_id


def test_e2e_pr_review():
    try:
        repo_name = "sweepai/e2e"  # for e2e test this is hardcoded
        installation_id = get_installation_id("sweepai")
        pr_number = 1349
        _, g = get_github_client(installation_id)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        
        review_pr(
            "E2E-test-user",
            pr,
            repo,
            installation_id,
            pr_labelled=True,
        )
    except AssertionError as e:
        for thread in global_threads:
            thread.join()
        print(f"Assertions failed with error: {e}")
        sys.exit(1)
    except Exception as e:
        for thread in global_threads:
            thread.join()
        stack_trace = traceback.format_exc()
        print(f"Failed with error: {e}\nTraceback: {stack_trace}")
        sys.exit(1)


if __name__ == "__main__":
    test_e2e_pr_review()
