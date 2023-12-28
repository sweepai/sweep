import time

from git import GitCommandError
from github.PullRequest import PullRequest
from loguru import logger

from sweepai.agents.pr_description_bot import PRDescriptionBot
from sweepai.core import entities
from sweepai.core.entities import FileChangeRequest
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.create_pr import create_pr_changes
from sweepai.handlers.on_ticket import get_branch_diff_text, sweeping_gif
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.progress import TicketContext, TicketProgress, TicketProgressStatus
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.str_utils import to_branch_name
from sweepai.utils.ticket_utils import center


def on_merge_conflict(
    pr_number: int,
    username: str,
    repo_full_name: str,
    installation_id: int,
    tracking_id: str,
):
    # copied from stack_pr
    token, g = get_github_client(installation_id=installation_id)
    repo = g.get_repo(repo_full_name)
    pr: PullRequest = repo.get_pull(pr_number)
    branch = pr.head.ref

    status_message = center(
        f"{sweeping_gif}\n\n"
        + f'Resolving merge conflicts: track the progress <a href="https://progress.sweep.dev/issues/{tracking_id}">here</a>.'
    )
    header = f"{status_message}\n---\n\nI'm currently resolving the merge conflicts in this PR. I will stack a new PR once I'm done."
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

    request = f"Sweep: Resolve merge conflicts for PR #{pr_number}: {pr.title}"
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

    chat_logger = ChatLogger(
        data={"username": username, "metadata": metadata, "tracking_id": tracking_id}
    )

    is_paying_user = chat_logger.is_paying_user()
    is_consumer_tier = chat_logger.is_consumer_tier()
    issue_url = pr.html_url

    edit_comment("Configuring branch...")

    new_pull_request = entities.PullRequest(
        title=title,
        branch_name="sweep/" + branch + "-merge-conflict",
        content="",
    )

    # Merge into base branch from cloned_repo.repo_dir to pr.base.ref
    git_repo = cloned_repo.git_repo
    old_head_branch = git_repo.branches[branch]
    head_branch = git_repo.create_head(
        new_pull_request.branch_name,
        commit=old_head_branch.commit,
    )
    head_branch.checkout()
    try:
        git_repo.git.merge("origin/" + pr.base.ref)
    except GitCommandError:
        # Assume there are merge conflicts
        pass

    git_repo.git.add(update=True)
    git_repo.git.commit()

    origin = git_repo.remotes.origin
    new_url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
    origin.set_url(new_url)
    git_repo.git.push("--set-upstream", origin, new_pull_request.branch_name)

    last_commit = git_repo.head.commit
    all_files = [item.a_path for item in last_commit.diff("HEAD~1")]
    conflict_files = []
    for file in all_files:
        contents = open(cloned_repo.repo_dir + "/" + file).read()
        if "\n<<<<<<<" in contents and "\n>>>>>>>" in contents:
            conflict_files.append(file)

    snippets = []
    for conflict_file in conflict_files:
        contents = open(cloned_repo.repo_dir + "/" + conflict_file).read()
        snippet = entities.Snippet(
            file_path=conflict_file,
            start=0,
            end=len(contents.splitlines()),
            content=contents,
        )
        snippets.append(snippet)
    tree = ""

    ticket_progress.status = TicketProgressStatus.PLANNING
    ticket_progress.save()

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
        branch=new_pull_request.branch_name,
    )
    # can select more precise snippets
    file_change_requests = [
        FileChangeRequest(
            filename=conflict_file,
            instructions="Resolve the merge conflicts by combining features from both branches into the final code or selecting one of the versions.",
            change_type="modify",
        )
        for conflict_file in conflict_files
    ]

    ticket_progress.status = TicketProgressStatus.CODING
    ticket_progress.save()
    edit_comment("Resolving merge conflicts...")
    generator = create_pr_changes(
        file_change_requests,
        new_pull_request,
        sweep_bot,
        username,
        installation_id,
        pr_number,
        chat_logger=chat_logger,
        base_branch=new_pull_request.branch_name,
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
        logger.info("Status", file_change_request.status == "succeeded")

    ticket_progress.status = TicketProgressStatus.COMPLETE
    ticket_progress.save()
    edit_comment("Done creating pull request.")

    diff_text = get_branch_diff_text(repo, new_pull_request.branch_name)
    # Can skip this step too
    new_description = PRDescriptionBot().describe_diffs(
        diff_text,
        new_pull_request.title,
    )
    new_description += f"\n\nResolves merge conflicts in #{pr_number}."

    # Create pull request
    new_pull_request.content = new_description
    github_pull_request = repo.create_pull(
        title=request,
        body=new_description,
        head=new_pull_request.branch_name,
        base=branch,
    )

    ticket_progress.context.pr_id = github_pull_request.number
    ticket_progress.context.done_time = time.time()
    ticket_progress.save()
    edit_comment(f"✨ **Created Pull Request:** {github_pull_request.html_url}")

    return {"success": True}


if __name__ == "__main__":
    on_merge_conflict(
        pr_number=2819,
        username="kevinlu1248",
        repo_full_name="sweepai/sweep",
        installation_id=36855882,
        tracking_id="test_merge_conflict",
    )
