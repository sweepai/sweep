import datetime
import json
import os
import sys
import time

from fastapi.testclient import TestClient
from github import Github
from github.PaginatedList import PaginatedList
from github.PullRequest import PullRequest

from sweepai.api import app, global_threads

g = Github(os.environ["GITHUB_PAT"])
repo_name = "sweepai/e2e"  # for e2e test this is hardcoded
repo = g.get_repo(repo_name)

local_tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo


def e2e_test_base(issue_json):
    client = TestClient(app)
    try:
        issue_title = issue_json["issue"]["title"]
        start_time = time.time()
        response = client.post(
            "/",
            json=issue_json,
            headers={"X-GitHub-Event": "issues"},
        )
        print(f"Completed in {time.time() - start_time}s")
        assert response
        assert response.text
        response_text = json.loads(response.text)
        assert response.status_code == 200
        assert "success" in response_text
        # poll github 15 times, waiting 1 minute between each poll, check if the pr has been created successfully or not
        for i in range(15):
            pulls: PaginatedList[PullRequest] = repo.get_pulls(
                state="open", sort="created", direction="desc"
            )
            # iterate through the top 5 pull requests and check if the title matches the expected title
            for pr in pulls[: min(5, pulls.totalCount)]:
                current_date = time.time() - 60 * (i + 2)
                current_date = datetime.datetime.fromtimestamp(current_date)
                creation_date: datetime.datetime = pr.created_at.replace(
                    tzinfo=datetime.timezone.utc
                ).astimezone(local_tz)
                # success if a new pr was made within i+1 minutes ago
                if (
                    issue_title in pr.title
                    and creation_date.timestamp() > current_date.timestamp()
                ):
                    for thread in global_threads:
                        thread.join()
                    print(f"PR created successfully: {pr.title}")
                    print(f"PR object is: {pr}")
                    return pr
            time.sleep(60)
        raise AssertionError("PR not created")
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


def test_e2e_change_button_color():
    issue_json = json.load(open("tests/jsons/e2e_button_to_green.json", "r"))
    e2e_test_base(issue_json)


def test_e2e_branch_change():
    issue_json = json.load(open("tests/jsons/e2e_branch_change.json", "r"))
    pr = e2e_test_base(issue_json)
    try:
        assert pr.base.ref == "dev"  # check hardcoded value
    except AssertionError as e:
        print(f"Assertaion that pr.base.ref == dev failed with: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_e2e_change_button_color()
    test_e2e_branch_change()
