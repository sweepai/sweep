import datetime
import json
import os
import sys
import time

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
pr_number = 19


def test_e2e_pr_comment():
    client = TestClient(app)
    try:
        issue_json = json.load(open("tests/jsons/e2e_pr_comment.json", "r"))
        issue_json["issue"]["title"]
        start_time = time.time()
        response = client.post(
            "/",
            json=issue_json,
            headers={"X-GitHub-Event": "issue_comment"},
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
            # iterate through the comments of the pr and check if a new comment got created the title Wrote Changes
            # get last 5 comments
            comments = pr.get_issue_comments()
            slicer = max(0, comments.totalCount - 5)
            for comment in comments[slicer:]:
                current_date = time.time() - 60 * (i + 2)
                current_date = datetime.datetime.fromtimestamp(current_date)
                creation_date = comment.created_at.replace(
                    tzinfo=datetime.timezone.utc
                ).astimezone(local_tz)
                # success if a new pr was made within i+1 minutes ago
                if (
                    "Wrote Changes" in comment.body
                    and creation_date.timestamp() > current_date.timestamp()
                ):
                    i = 1
                    for thread in global_threads:
                        thread.join()
                        print(f"joining thread {i} of {len(global_threads)}")
                        i += 1
                    print(f"PR successfully updated: {pr.title}")
                    print(f"PR object is: {pr}")
                    return
                if (
                    "Could not find files to change" in comment.body
                    and creation_date.timestamp() > current_date.timestamp()
                ):
                    for thread in global_threads:
                        thread.join()
                    print(f"Failed to find files to change: {pr.title}")
                    print(f"PR object is: {pr}")
                    raise AssertionError("Failed to find files to change")
                    
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
        print(f"Failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_e2e_pr_comment()
