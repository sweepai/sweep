import time

from github.PullRequest import PullRequest
from loguru import logger

from sweepai.agents.pr_description_bot import PRDescriptionBot
from sweepai.core import entities
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.create_pr import create_pr_changes
from sweepai.handlers.on_ticket import get_branch_diff_text, sweeping_gif
from sweepai.utils.chat_logger import ChatLogger
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
    _token, g = get_github_client(installation_id=installation_id)
    repo = g.get_repo(repo_full_name)
    pr: PullRequest = repo.get_pull(pr_number)
    branch = pr.head.ref

    status_message = center(
        f"{sweeping_gif}\n\n"
        + f'Fixing PR: track the progress <a href="https://progress.sweep.dev/issues/{tracking_id}">here</a>.'
    )
    header = f"{status_message}\n---\n\nI'm currently fixing this PR to address the following:\n\n{blockquote(request)}"
    comment = pr.create_issue_comment(body=header)

    def edit_comment(body):
        nonlocal comment
        comment.edit(header + "\n\n" + body)

    cloned_repo = ClonedRepo(
        repo_full_name=repo_full_name,
        installation_id=installation_id,
        branch=branch,
    )
    metadata = {}
    start_time = time.time()

    title = request
    if len(title) > 50:
        title = title[:50] + "..."
    ticket_progress = TicketProgress(
        tracking_id=tracking_id,
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

    chat_logger = ChatLogger(
        data={"username": username, "metadata": metadata, "tracking_id": tracking_id}
    )

    is_paying_user = chat_logger.is_paying_user()
    is_consumer_tier = chat_logger.is_consumer_tier()
    issue_url = pr.html_url

    edit_comment("Currently fetching files... (step 0/3)")

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
            " Perhaps the repo has not been initialized. If this error persists"
            f" contact team@sweep.dev.\n\n> @{username}, editing this issue description to include more details will automatically make me relaunch. Please join our Discord server for support (tracking_id={tracking_id})"
        )
        raise Exception("Failed to fetch files")

    ticket_progress.status = TicketProgressStatus.PLANNING
    ticket_progress.save()
    edit_comment("Generating plan by analyzing files... (step 1/3)")

    human_message = HumanMessagePrompt(
        repo_name=repo_full_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo.description.strip(),
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
    file_change_requests, plan = sweep_bot.get_files_to_change(snippets, cloned_repo)

    ticket_progress.status = TicketProgressStatus.CODING
    ticket_progress.save()
    edit_comment("Making changes according to plan... (step 2/3)")
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
        logger.info("Status", file_change_request.succeeded)

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
        base=pr.head.ref,
    )

    ticket_progress.context.pr_id = github_pull_request.number
    ticket_progress.context.done_time = time.time()
    ticket_progress.save()
    edit_comment(f"✨ **Created Pull Request:** {github_pull_request.html_url}")

    return {"success": True}


if __name__ == "__main__":
    stack_pr(
        request="Add type hints to create_payment_messages in on_ticket.py.",
        pr_number=2646,
        username="kevinlu1248",
        repo_full_name="sweepai/sweep",
        installation_id=36855882,
        tracking_id="test_stack_pr",
    )
