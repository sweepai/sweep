import modal
import openai
from github.Repository import Repository
from loguru import logger

from sweepai.core.entities import FileChangeRequest, PullRequest
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.config.server import GITHUB_DEFAULT_CONFIG, OPENAI_API_KEY, PREFIX, DB_MODAL_INST_NAME, GITHUB_BOT_TOKEN, \
    GITHUB_BOT_USERNAME, \
    GITHUB_CONFIG_BRANCH
from sweepai.core.sweep_bot import SweepBot, MaxTokensExceeded
from sweepai.utils.event_logger import posthog

github_access_token = GITHUB_BOT_TOKEN
openai.api_key = OPENAI_API_KEY

update_index = modal.Function.lookup(DB_MODAL_INST_NAME, "update_index")

num_of_snippets_to_query = 10
max_num_of_snippets = 5


def create_pr(
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
        pull_request.branch_name = sweep_bot.create_branch(pull_request.branch_name)
        completed_count, fcr_count = sweep_bot.change_files_in_github(file_change_requests, pull_request.branch_name)
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
            return {"success": False, "error": "No changes made"}

        # Include issue number in PR description
        if issue_number:
            # If the #issue changes, then change on_ticket (f'Fixes #{issue_number}.\n' in pr.body:)
            pr_description = f"{pull_request.content}\n\nFixes #{issue_number}.\n\nTo checkout this PR branch, run the following command in your terminal:\n```zsh\ngit checkout {pull_request.branch_name}\n```"
        else:
            pr_description = f"{pull_request.content}\n\nTo checkout this PR branch, run the following command in your terminal:\n```zsh\ngit checkout {pull_request.branch_name}\n```"

        pr = sweep_bot.repo.create_pull(
            title=pull_request.title,
            body=pr_description,
            head=pull_request.branch_name,
            base=SweepConfig.get_branch(sweep_bot.repo),
        )
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
    if sweep_bot.chat_logger is not None:
        sweep_bot.chat_logger.add_successful_ticket()
    return {"success": True, "pull_request": pr}


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
    title = "Create `sweep.yaml` Config File"
    branch_name = GITHUB_CONFIG_BRANCH
    branch_name = sweep_bot.create_branch(branch_name, retry=False)
    try:
        sweep_bot.repo.create_file(
            'sweep.yaml',
            'Create sweep.yaml config file',
            GITHUB_DEFAULT_CONFIG.format(branch=sweep_bot.repo.default_branch),
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
        Thank you for using Sweep! 🧹
        """,
        head=branch_name,
        base=SweepConfig.get_branch(sweep_bot.repo),
    )

    return pr
