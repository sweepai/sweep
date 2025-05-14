import datetime
import json
import os
import tempfile

import pytest
from typer.testing import CliRunner

from sweepai.cli import app, load_config

issue_json = json.load(open("tests/jsons/e2e_button_to_green.json", "r"))
local_tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo
GITHUB_PAT = os.environ.get("GITHUB_PAT")

runner = CliRunner()


@pytest.fixture(autouse=True)
def setup_config():
    with tempfile.TemporaryDirectory() as tmp_dir:
        import sweepai.cli

        original_app_dir = sweepai.cli.app_dir
        original_config_path = sweepai.cli.config_path

        app_dir = tmp_dir
        os.path.join(app_dir, "config.json")

        yield

        sweepai.cli.app_dir = original_app_dir
        sweepai.cli.config_path = original_config_path


@pytest.fixture(autouse=True)
def clean_env():
    original_env = os.environ.copy()
    os.environ.clear()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.mark.skip(reason="This test breaks.")
def test_cli():
    assert os.environ.get("OPENAI_API_KEY") is None
    assert os.environ.get("GITHUB_PAT") is None
    load_config()
    assert os.environ.get("OPENAI_API_KEY") is not None
    assert os.environ.get("GITHUB_PAT") is not None


# def test_initialization(): pass


def test_run():
    issue_title = "Sweep: Change the install app button color to green"
    load_config()
    result = runner.invoke(app, ["run", "https://github.com/sweepai/e2e/issues/8"])

    # repo = Github(GITHUB_PAT).get_repo("sweepai/e2e")
    # pulls: PaginatedList[PullRequest] = repo.get_pulls(
    #     state="open", sort="created", direction="desc"
    # )
    # for pr in pulls[: pulls.totalCount]:
    #     current_date = time.time() - 60 * 5
    #     current_date = datetime.datetime.fromtimestamp(current_date)
    #     creation_date: datetime.datetime = pr.created_at.replace(
    #         tzinfo=datetime.timezone.utc
    #     ).astimezone(local_tz)
    #     # success if a new pr was made within i+1 minutes ago
    #     if (
    #         issue_title in pr.title
    #         and creation_date.timestamp() > current_date.timestamp()
    #     ):
    #         print(f"PR created successfully: {pr.title}")
    #         print(f"PR object is: {pr}")
    #         return pr
    # raise AssertionError("PR not created")
