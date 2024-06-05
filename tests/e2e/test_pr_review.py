import datetime
import json
import os
import sys
import time
import traceback

from fastapi.testclient import TestClient
from github import Github

from sweepai.api import app, global_threads

GITHUB_PAT = os.environ["GITHUB_PAT"]
print(
    f"Using GITHUB_PAT: "
    + GITHUB_PAT[:3]
    + "*" * (len(GITHUB_PAT) - 4)
    + GITHUB_PAT[-1:]
)
g = Github(GITHUB_PAT)
repo_name = "sweepai/e2e"  # for e2e test this is hardcoded
repo = g.get_repo(repo_name)

local_tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
# PR NUMBER is hardcoded for e2e test
pr_number = 1349


def test_e2e_pr_review():
    client = TestClient(app)
    try:
        issue_json = json.load(open("tests/jsons/e2e_pr_review.json", "r"))
        start_time = time.time()
        response = client.post(
            "/",
            json=issue_json,
            headers={"X-GitHub-Event": "pull_request"},
        )
        print(f"Completed in {time.time() - start_time}s")
        assert response
        assert response.text
        response_text = json.loads(response.text)
        assert response.status_code == 200
        assert "success" in response_text
        pr = repo.get_pull(pr_number)
        # poll github 20 times, waiting 1 minute between each poll, check if the pr has been updated or not
        for i in range(20):
            pr = repo.get_pull(pr_number)
            # iterate through the comments of the pr and check if a new comment got created the title Sweep: PR Review
            comments = pr.get_issue_comments()
            for comment in comments:
                # success if a new pr was made within i+1 minutes ago
                if (
                    "Sweep: PR Review" in comment.body
                ):
                    i = 1
                    for thread in global_threads:
                        thread.join()
                        print(f"joining thread {i} of {len(global_threads)}")
                        i += 1
                    print(f"PR successfully updated: {pr.title}")
                    print(f"PR object is: {pr}")
                    # delete comment for next time around
                    comment.delete()
                    return
                    
            time.sleep(60)
        raise AssertionError("PR was not updated!")
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
