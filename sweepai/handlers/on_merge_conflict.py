import time
import traceback

from git import GitCommandError
from github.PullRequest import PullRequest
from loguru import logger

from sweepai.core import entities
from sweepai.core.entities import FileChangeRequest
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.create_pr import create_pr_changes
from sweepai.handlers.on_ticket import get_branch_diff_text, sweeping_gif
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.progress import TicketContext, TicketProgress, TicketProgressStatus
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.str_utils import to_branch_name
from sweepai.utils.ticket_utils import center

instructions_format = """Resolve the merge conflicts in the PR by incorporating changes from both branches into the final code.

Title of PR: {title}

Here were the original changes to this file in the head branch:
Commit message: {head_commit_message}
```diff
{head_diff}
```

Here were the original changes to this file in the base branch:
Commit message: {base_commit_message}
```diff
{base_diff}
```

In the analysis_and_identification, first determine what each change does. Then determine what the final code should be. Then, use the keyword_search to find the merge conflict markers <<<<<<< and >>>>>>>. Finally, make the code changes by writing the old_code and the new_code."""


def on_merge_conflict(
    pr_number: int,
    username: str,
    repo_full_name: str,
    installation_id: int,
    tracking_id: str,
):
    # copied from stack_pr
    token, g = get_github_client(installation_id=installation_id)
    try:
        repo = g.get_repo(repo_full_name)
    except Exception as e:
        print("Exception occured while getting repo", e)
        pass
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

    try:
        cloned_repo = ClonedRepo(
            repo_full_name=repo_full_name,
            installation_id=installation_id,
            branch=branch,
            token=token,
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
            data={
                "username": username,
                "metadata": metadata,
                "tracking_id": tracking_id,
            }
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

        # Making sure name is unique
        for i in range(30):
            try:
                repo.get_branch(new_pull_request.branch_name + "_" + str(i))
            except Exception:
                new_pull_request.branch_name += "_" + str(i)
                break

        # Merge into base branch from cloned_repo.repo_dir to pr.base.ref
        git_repo = cloned_repo.git_repo
        old_head_branch = git_repo.branches[branch]
        head_branch = git_repo.create_head(
            new_pull_request.branch_name,
            commit=old_head_branch.commit,
        )
        head_branch.checkout()
        try:
            git_repo.config_writer().set_value('user','name', 'sweep-nightly[bot]').release()
            git_repo.config_writer().set_value('user','email', 'team@sweep.dev').release()
            git_repo.git.merge("origin/" + pr.base.ref)
        except GitCommandError as e:
            # Assume there are merge conflicts
            pass

        git_repo.git.add(update=True)
        # -m and message are needed otherwise exception is thrown
        git_repo.git.commit('-m', 'commit with merge conflict')

        origin = git_repo.remotes.origin
        new_url = f"https://x-access-token:{token}@github.com/{repo_full_name}.git"
        origin.set_url(new_url)
        git_repo.git.push("--set-upstream", origin, new_pull_request.branch_name)

        last_commit = git_repo.head.commit
        all_files = [item.a_path for item in last_commit.diff("HEAD~1")]
        conflict_files = []
        for file in all_files:
            try:
                contents = open(cloned_repo.repo_dir + "/" + file).read()
                if "\n<<<<<<<" in contents and "\n>>>>>>>" in contents:
                    conflict_files.append(file)
            except UnicodeDecodeError:
                pass

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
        file_change_requests = []

        base_commits = pr.base.repo.get_commits().get_page(0)
        head_commits = list(pr.get_commits())
        for conflict_file in conflict_files:
            old_code = repo.get_contents(
                conflict_file, ref=head_commits[0].parents[0].sha
            ).decoded_content.decode()
            base_code = repo.get_contents(
                conflict_file, ref=pr.base.ref
            ).decoded_content.decode()
            head_code = repo.get_contents(
                conflict_file, ref=pr.head.ref
            ).decoded_content.decode()
            base_diff = generate_diff(old_code=old_code, new_code=base_code)
            head_diff = generate_diff(old_code=old_code, new_code=head_code)
            base_commit_message = ""
            for commit in base_commits[::-1]:
                if any(
                    commit_file.filename == conflict_file
                    for commit_file in commit.files
                ):
                    base_commit_message = commit.raw_data["commit"]["message"]
                    break
            head_commit_message = ""
            for commit in head_commits[::-1]:
                if any(
                    commit_file.filename == conflict_file
                    for commit_file in commit.files
                ):
                    head_commit_message = commit.raw_data["commit"]["message"]
                    break
            file_change_requests.append(
                FileChangeRequest(
                    filename=conflict_file,
                    instructions=instructions_format.format(
                        title=pr.title,
                        base_commit_message=base_commit_message,
                        base_diff=base_diff,
                        head_commit_message=head_commit_message,
                        head_diff=head_diff,
                    ),
                    change_type="modify",
                )
            )

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
        # new_description = PRDescriptionBot().describe_diffs(
        #     diff_text,
        #     new_pull_request.title,
        # )
        # new_description += f"\n\nResolves merge conflicts in #{pr_number}."
        new_description = f"This PR resolves the merge conflicts in #{pr_number}. This branch can be directly merged into {pr.base.ref}."

        # Create pull request
        new_pull_request.content = new_description
        github_pull_request = repo.create_pull(
            title=request,
            body=new_description,
            head=new_pull_request.branch_name,
            base=pr.base.ref,
        )

        ticket_progress.context.pr_id = github_pull_request.number
        ticket_progress.context.done_time = time.time()
        ticket_progress.save()
        edit_comment(f"✨ **Created Pull Request:** {github_pull_request.html_url}")

        return {"success": True}
    except Exception as e:
        print(f"Exception occured: {e}")
        edit_comment(
            f"> [!CAUTION]\n> \nAn error has occurred: {str(e)} (tracking ID: {tracking_id})"
        )
        discord_log_error(
            "Error occured in on_merge_conflict.py" + 
            traceback.format_exc()
            + "\n\n"
            + str(e)
            + "\n\n"
            + f"tracking ID: {tracking_id}"
        )
        return {"success": False}


if __name__ == "__main__":
    on_merge_conflict(
        pr_number=66,
        username="MartinYe1234",
        repo_full_name="MartinYe1234/Chess-Game",
        installation_id=45945746,
        tracking_id="martin_private_test_merge_conflict",
    )
