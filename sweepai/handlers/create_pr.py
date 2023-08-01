import modal
import openai
from github.Repository import Repository
from loguru import logger

from sweepai.core.entities import FileChangeRequest, PullRequest, MockPR
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.config.server import GITHUB_DEFAULT_CONFIG, GITHUB_LABEL_NAME, OPENAI_API_KEY, PREFIX, DB_MODAL_INST_NAME, GITHUB_BOT_TOKEN, \
    GITHUB_BOT_USERNAME, \
    GITHUB_CONFIG_BRANCH
from sweepai.utils.github_utils import get_github_client
from sweepai.core.sweep_bot import SweepBot, MaxTokensExceeded
from sweepai.utils.event_logger import posthog

github_access_token = GITHUB_BOT_TOKEN
openai.api_key = OPENAI_API_KEY

update_index = modal.Function.lookup(DB_MODAL_INST_NAME, "update_index")

num_of_snippets_to_query = 10
max_num_of_snippets = 5


def create_pr_changes(
        file_change_requests: list[FileChangeRequest],
        pull_request: PullRequest,
        sweep_bot: SweepBot,
        username: str,
        installation_id: int,
        issue_number: int | None = None
):
    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR
    chat_logger = ChatLogger({
    "username": username,
    "installation_id": installation_id,
    "repo_full_name": sweep_bot.repo.full_name,
    "title": pull_request.title,
    "summary": "",
    "issue_url": ""})
    sweep_bot.chat_logger = chat_logger
    organization, repo_name = sweep_bot.repo.full_name.split("/")
    metadata = {
        "repo_full_name": sweep_bot.repo.full_name,
        "organization": organization,
        "repo_name": repo_name,
        "repo_description": sweep_bot.repo.description,
        "username": username,
        "installation_id": installation_id,
        "function": "on_ticket",
        "mode": PREFIX,
    }
    posthog.capture(username, "started", properties=metadata)

    try:
        logger.info("Making PR...")
        pull_request.branch_name = sweep_bot.git_hosting_service.create_branch(pull_request.branch_name)
        completed_count, fcr_count = sweep_bot.git_hosting_service.change_files(file_change_requests, pull_request.branch_name)
        if completed_count == 0 and fcr_count != 0:
            logger.info("No changes made")
            posthog.capture(
                username,
                "failed",
                properties={
                    "error": "No changes made",
                    "reason": "No changes made",
                    **metadata,
                },
            )

            # Todo: if no changes were made, delete branch
            commits = list(sweep_bot.repo.get_commits(pull_request.branch_name))
            if len(commits) == 0:
                branch = sweep_bot.repo.get_git_ref(f"heads/{pull_request.branch_name}")
                branch.delete()

            return {"success": False, "error": "No changes made"}
        # Include issue number in PR description
        if issue_number:
            # If the #issue changes, then change on_ticket (f'Fixes #{issue_number}.\n' in pr.body:)
            pr_description = f"{pull_request.content}\n\nFixes #{issue_number}.\n\nTo checkout this PR branch, run the following command in your terminal:\n```zsh\ngit checkout {pull_request.branch_name}\n```"
        else:
            pr_description = f"{pull_request.content}\n\nTo checkout this PR branch, run the following command in your terminal:\n```zsh\ngit checkout {pull_request.branch_name}\n```"
        pr_title = pull_request.title
        if "sweep.yaml" in pr_title:
            pr_title = "[config] " + pr_title

        pr = sweep_bot.git_hosting_service.create_pull_request(
            title="[DRAFT] " + pr_title,
            body=pr_description,
            head=pull_request.branch_name,
            base=SweepConfig.get_branch(sweep_bot.repo),
        )
        pr.add_labels(GITHUB_LABEL_NAME)
    except MaxTokensExceeded as e:
        logger.error(e)
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Max tokens exceeded",
                **metadata,
            },
        )
        raise e
    except openai.error.InvalidRequestError as e:
        logger.error(e)
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Invalid request error / context length",
                **metadata,
            },
        )
        raise e
    except Exception as e:
        logger.error(e)
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Unexpected error",
                **metadata,
            },
        )
        raise e

    posthog.capture(username, "success", properties={**metadata})
    logger.info("create_pr success")
    return {"success": True, "pull_request": MockPR(file_count=completed_count, title=pr_title, body=pr_description, pr_head=pull_request.branch_name,
                                                    base=sweep_bot.repo.get_branch(SweepConfig.get_branch(sweep_bot.repo)).commit,
                                                    head=sweep_bot.repo.get_branch(pull_request.branch_name).commit)}


def safe_delete_sweep_branch(
        pr,  # Github PullRequest
        repo: Repository,
) -> bool:
    """
    Safely delete Sweep branch
    1. Only edited by Sweep
    2. Prefixed by sweep/
    """
    pr_commits = pr.get_commits()
    pr_commit_authors = set([commit.author.login for commit in pr_commits])

    # Check if only Sweep has edited the PR, and sweep/ prefix
    if len(pr_commit_authors) == 1 \
            and GITHUB_BOT_USERNAME in pr_commit_authors \
            and pr.head.ref.startswith("sweep/"):
        branch = repo.get_git_ref(f"heads/{pr.head.ref}")
        # pr.edit(state='closed')
        branch.delete()
        return True
    else:
        # Failed to delete branch as it was edited by someone else
        return False


def create_config_pr(
        sweep_bot: SweepBot,
):
    title = "Configure Sweep"
    branch_name = GITHUB_CONFIG_BRANCH
    branch_name = sweep_bot.create_branch(branch_name, retry=False)
    try:
        sweep_bot.repo.create_file(
            'sweep.yaml',
            'Create sweep.yaml config file',
            GITHUB_DEFAULT_CONFIG.format(branch=sweep_bot.repo.default_branch),
            branch=branch_name
        )
        sweep_bot.repo.create_file(
            '.github/ISSUE_TEMPLATE/sweep-bugfix.yml',
            'Create bugfix template',
            BUGFIX_TEMPLATE,
            branch=branch_name
        )
        sweep_bot.repo.create_file(
            '.github/ISSUE_TEMPLATE/sweep-feature.yml',
            'Create feature template',
            FEATURE_TEMPLATE,
            branch=branch_name
        )
        sweep_bot.repo.create_file(
            '.github/ISSUE_TEMPLATE/sweep-refactor.yml',
            'Create refactor template',
            REFACTOR_TEMPLATE,
            branch=branch_name
        )
    except Exception as e:
        logger.error(e)

    # Check if the pull request from this branch to main already exists.
    # If it does, then we don't need to create a new one.
    pull_requests = sweep_bot.repo.get_pulls(
        state="open",
        sort="created",
        base=SweepConfig.get_branch(sweep_bot.repo),
        head=branch_name,
    )
    for pr in pull_requests:
        if pr.title == title:
            return pr

    pr = sweep_bot.repo.create_pull(
        title=title,
        body=
        """🎉 Thank you for installing Sweep! We're thrilled to announce the latest update for Sweep, your trusty AI junior developer on GitHub. This PR creates a `sweep.yaml` config file, allowing you to personalize Sweep's performance according to your project requirements.

## What's new?
- **Sweep is now configurable**. 
- To configure Sweep, simply edit the `sweep.yaml` file in the root of your repository.
- If you need help, check out the [Sweep Default Config](https://github.com/sweepai/sweep/blob/main/sweep.yaml) or [Join Our Discord](https://discord.gg/sweep-ai) for help.

If you would like me to stop creating this PR, go to issues and say "Sweep: create an empty `sweep.yaml` file".
Thank you for using Sweep! 🧹""",
        head=branch_name,
        base=SweepConfig.get_branch(sweep_bot.repo),
    )
    pr.add_to_labels(GITHUB_LABEL_NAME)
    return pr

def create_gha_pr(g, repo):
    # Create a new branch
    branch_name = "sweep/gha-enable"
    branch = repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=repo.get_branch(repo.default_branch).commit.sha)

    # Update the sweep.yaml file in this branch to add "gha_enabled: True"
    sweep_yaml_content = repo.get_contents("sweep.yaml", ref=branch_name).decoded_content.decode() + "\ngha_enabled: True"
    repo.update_file("sweep.yaml", "Enable GitHub Actions", sweep_yaml_content, repo.get_contents("sweep.yaml", ref=branch_name).sha, branch=branch_name)

    # Create a PR from this branch to the main branch
    pr = repo.create_pull(title="Enable GitHub Actions", body="This PR enables GitHub Actions for this repository.", head=branch_name, base=repo.default_branch)
    return pr

REFACTOR_TEMPLATE = """\
name: Refactor
title: 'Sweep: '
description: Write something like "Modify the ... api endpoint to use ... version and ... framework"
labels: sweep
body:
  - type: textarea
    id: description
    attributes:
      label: Details
      description: More details for Sweep
      placeholder: We are migrating this function to ... version because ..."""

BUGFIX_TEMPLATE = """\
name: Bugfix
title: 'Sweep: '
description: Write something like "We notice ... behavior when ... happens instead of ...""
labels: sweep
body:
  - type: textarea
    id: description
    attributes:
      label: Details
      description: More details about the bug
      placeholder: The bug might be in ... file"""

FEATURE_TEMPLATE = """\
name: Feature Request
title: 'Sweep: '
description: Write something like "Write an api endpoint that does "..." in the "..." file"
labels: sweep
body:
  - type: textarea
    id: description
    attributes:
      label: Details
      description: More details for Sweep
      placeholder: The new endpoint should use the ... class from ... file because it contains ... logic"""