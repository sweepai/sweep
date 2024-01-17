import time
import traceback

from github.PullRequest import PullRequest
from loguru import logger

from sweepai.agents.pr_description_bot import PRDescriptionBot
from sweepai.core import entities
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.create_pr import create_pr_changes
from sweepai.handlers.on_ticket import get_branch_diff_text, sweeping_gif
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.progress import TicketContext, TicketProgress, TicketProgressStatus
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.str_utils import blockquote, to_branch_name
from sweepai.utils.ticket_utils import center, fetch_relevant_files


def stack_pr(
    request: str,
    pr_number: int,
    username: str,
    repo_full_name: str,
    installation_id: int,
    tracking_id: str,
):
    token, g = get_github_client(installation_id=installation_id)
    repo = g.get_repo(repo_full_name)
    pr: PullRequest = repo.get_pull(pr_number)
    branch = pr.head.ref

    if pr.state != "open":
        return {
            "success": False,
            "error_message": "This PR is not open, so I won't attempt to fix it.",
        }

    if (
        sum(
            [
                comment.user.login.startswith("sweep-")
                for comment in pr.get_issue_comments()
            ]
        )
        > 3
    ):
        return {
            "success": False,
            "error_message": "It looks like there are already Sweep comments on this PR, so I won't attempt to fix it.",
        }

    status_message = center(
        f"{sweeping_gif}\n\n"
        + f'Fixing PR: track the progress <a href="https://progress.sweep.dev/issues/{tracking_id}">here</a>.'
    )
    header = f"{status_message}\n---\n\nI'm currently fixing this PR to address the following:\n\n{blockquote(request)}"
    comment = pr.create_issue_comment(body=header)
    metadata = {}

    def edit_comment(body):
        nonlocal comment
        comment.edit(header + "\n\n" + body)

    try:
        cloned_repo = ClonedRepo(
            repo_full_name=repo_full_name,
            installation_id=installation_id,
            token=token,
            branch=branch,
        )
        start_time = time.time()

        title = request
        if len(title) > 50:
            title = title[:50] + "..."
        ticket_progress = TicketProgress(
            tracking_id=tracking_id,
            username=username,
            context=TicketContext(
                title=title,
                description="",
                repo_full_name=repo_full_name,
                branch_name="sweep/" + to_branch_name(request),
                issue_number=pr_number,
                is_public=repo.private is False,
                start_time=time.time(),
            ),
        )

        metadata = {
            "tracking_id": tracking_id,
            "username": username,
            "function": "stack_pr",
            **ticket_progress.context.dict(),
        }
        posthog.capture(
            username,
            "started",
            properties=metadata,
        )

        chat_logger = ChatLogger(
            data={
                "username": username,
                "metadata": metadata,
                "tracking_id": tracking_id,
            }
        )

        is_paying_user = chat_logger.is_paying_user()
        is_consumer_tier = chat_logger.is_consumer_tier()
        issue_url = pr.html_url

        edit_comment("Currently fetching files... (step 1/3)")

        try:
            snippets, tree, _ = fetch_relevant_files(
                cloned_repo,
                request,
                "",
                "",
                username,
                metadata,
                start_time,
                tracking_id,
                is_paying_user,
                is_consumer_tier,
                issue_url,
                chat_logger,
                ticket_progress,
            )
        except:
            edit_comment(
                "It looks like an issue has occurred around fetching the files."
                " Perhaps the repo failed to initialized. If this error persists"
                f" contact team@sweep.dev.\n\n> @{username}, editing this issue description to include more details will automatically make me relaunch. Please join our Discord server for support (tracking_id={tracking_id})"
            )
            raise Exception("Failed to fetch files")

        ticket_progress.status = TicketProgressStatus.PLANNING
        ticket_progress.save()
        edit_comment("Generating plan by analyzing files... (step 2/3)")

        human_message = HumanMessagePrompt(
            repo_name=repo_full_name,
            issue_url=issue_url,
            username=username,
            repo_description=(repo.description or "").strip(),
            title=request,
            summary=request,
            snippets=snippets,
            tree=tree,
        )

        sweep_bot = SweepBot.from_system_message_content(
            human_message=human_message,
            repo=repo,
            ticket_progress=ticket_progress,
            chat_logger=chat_logger,
            cloned_repo=cloned_repo,
        )
        file_change_requests, plan = sweep_bot.get_files_to_change(
            snippets, cloned_repo
        )

        ticket_progress.status = TicketProgressStatus.CODING
        ticket_progress.save()
        edit_comment("Making changes according to plan... (step 3/3)")
        pull_request = entities.PullRequest(
            title=title,
            branch_name="sweep/" + to_branch_name(request),
            content="",
        )
        generator = create_pr_changes(
            file_change_requests,
            pull_request,
            sweep_bot,
            username,
            installation_id,
            pr_number,
            chat_logger=chat_logger,
            base_branch=branch,
        )

        for item in generator:
            if isinstance(item, dict):
                response = item
                break
            (
                file_change_request,
                changed_file,
                sandbox_response,
                commit,
                file_change_requests,
            ) = item
            logger.info("Status", file_change_request.status)

        ticket_progress.status = TicketProgressStatus.COMPLETE
        ticket_progress.save()
        edit_comment("Done creating pull request.")

        diff_text = get_branch_diff_text(repo, pull_request.branch_name)
        new_description = PRDescriptionBot().describe_diffs(
            diff_text,
            pull_request.title,
        )
        pull_request.content = new_description
        github_pull_request = repo.create_pull(
            title=pull_request.title,
            body=pull_request.content,
            head=pull_request.branch_name,
            base=branch,
        )

        ticket_progress.context.pr_id = github_pull_request.number
        ticket_progress.context.done_time = time.time()
        ticket_progress.save()
        edit_comment(f"✨ **Created Pull Request:** {github_pull_request.html_url}")
        posthog.capture(
            username,
            "success",
            properties=metadata,
        )
        return {"success": True}
    except Exception as e:
        edit_comment(
            f"> [!CAUTION]\n> \nAn error has occurred: {str(e)} (tracking ID: {tracking_id})"
        )
        discord_log_error(
            traceback.format_exc()
            + "\n\n"
            + str(e)
            + "\n\n"
            + f"tracking ID: {tracking_id}"
        )
        posthog.capture(
            username,
            "failed",
            properties=metadata,
        )
        return {"success": False}


if __name__ == "__main__":
    request = """Fix the GitHub Actions workflow for the repo:

The command:
Run pnpm run build
yielded the following error:
##[error]Process completed with exit code 1.

MongoParseError: Invalid scheme, expected connection string to start with "mongodb://" or "mongodb+srv://"
at new ConnectionString (/home/runner/work/ui/ui/node_modules/.pnpm/mongodb-connection-string-url@3.0.0/node_modules/mongodb-connection-string-url/lib/index.js:86:19)
at parseOptions (/home/runner/work/ui/ui/node_modules/.pnpm/mongodb@6.3.0/node_modules/mongodb/lib/connection_string.js:186:17)
at new MongoClient (/home/runner/work/ui/ui/node_modules/.pnpm/mongodb@6.3.0/node_modules/mongodb/lib/mongo_client.js:51:63)
at 24247 (/home/runner/work/ui/ui/.next/server/app/api/[tracking_id]/route.js:1:1325)
at t (/home/runner/work/ui/ui/.next/server/webpack-runtime.js:1:128)
at 47717 (/home/runner/work/ui/ui/.next/server/app/api/[tracking_id]/route.js:1:471)
at t (/home/runner/work/ui/ui/.next/server/webpack-runtime.js:1:128)
at o (/home/runner/work/ui/ui/.next/server/app/api/[tracking_id]/route.js:1:2997)
at /home/runner/work/ui/ui/.next/server/app/api/[tracking_id]/route.js:1:3024
at t.X (/home/runner/work/ui/ui/.next/server/webpack-runtime.js:1:1206)

> Build error occurred
Error: Failed to collect page data for /api/[tracking_id]
at /home/runner/work/ui/ui/node_modules/.pnpm/next@14.0.3_react-dom@18.0.0_react@18.0.0/node_modules/next/dist/build/utils.js:1217:15
at process.processTicksAndRejections (node:internal/process/task_queues:95:5) {
type: 'Error'
}
ELIFECYCLE  Command failed with exit code 1."""
    stack_pr(
        request=request,
        pr_number=32,
        username="kevinlu1248",
        repo_full_name="sweepai/ui",
        installation_id=36855882,
        tracking_id="fix_typeerror",
    )
