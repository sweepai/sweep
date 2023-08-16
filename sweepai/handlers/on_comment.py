import re
import traceback

import openai
from loguru import logger
from typing import Any
from tabulate import tabulate
from github.Repository import Repository

from sweepai.config.client import get_blocked_dirs

from sweepai.config.client import get_blocked_dirs


def construct_metadata(
    repo_full_name,
    repo_name,
    organization,
    repo_description,
    installation_id,
    username,
    function,
    model,
    tier,
    mode,
):
    return {
        "repo_full_name": repo_full_name,
        "repo_name": repo_name,
        "organization": organization,
        "repo_description": repo_description,
        "installation_id": installation_id,
        "username": username,
        "function": function,
        "model": model,
        "tier": tier,
        "mode": mode,
    }


from sweepai.core.entities import FileChangeRequest, NoFilesException, Snippet, MockPR
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs
from sweepai.utils.chat_logger import ChatLogger
from sweepai.config.server import (
    GITHUB_BOT_USERNAME,
    PREFIX,
    OPENAI_API_KEY,
    GITHUB_BOT_TOKEN,
)
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import (
    get_github_client,
    search_snippets,
)
from sweepai.utils.prompt_constructor import HumanMessageCommentPrompt

github_access_token = GITHUB_BOT_TOKEN
openai.api_key = OPENAI_API_KEY

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2
num_extended_snippets = 2


def post_process_snippets(snippets: list[Snippet], max_num_of_snippets: int = 3):
    for snippet in snippets[:num_full_files]:
        snippet = snippet.expand()

    # snippet fusing
    i = 0
    while i < len(snippets):
        j = i + 1
        while j < len(snippets):
            if snippets[i] ^ snippets[j]:  # this checks for overlap
                snippets[i] = snippets[i] | snippets[j]  # merging
                snippets.pop(j)
            else:
                j += 1
        i += 1

    # truncating snippets based on character length
    result_snippets = []
    total_length = 0
    for snippet in snippets:
        total_length += len(snippet.get_snippet())
        if total_length > total_number_of_snippet_tokens * 5:
            break
        result_snippets.append(snippet)
    return result_snippets[:max_num_of_snippets]


def on_comment(
    repo_full_name: str,
    repo_description: str,
    comment: str,
    pr_path: str | None,
    pr_line_position: int | None,
    username: str,
    installation_id: int,
    pr_number: int = None,
    comment_id: int | None = None,
    g: None = None,
    repo: Repository = None,
    pr: Any = None,  # Uses PRFileChanges type too
    chat_logger: Any = None,
):
    # Check if the comment is "REVERT"
    if comment.strip().upper() == "REVERT":
        rollback_file(repo_full_name, pr_path, installation_id, pr_number)
        return {
            "success": True,
            "message": "File has been reverted to the previous commit.",
        }

    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR
    logger.info(
        f"Calling on_comment() with the following arguments: {comment}, {repo_full_name}, {repo_description}, {pr_path}"
    )
    organization, repo_name = repo_full_name.split("/")

    g = (get_github_client(installation_id))[1] if not g else g
    repo = g.get_repo(repo_full_name) if not repo else repo
    pr = repo.get_pull(pr_number) if not pr else pr
    pr_title = pr.title
    pr_body = pr.body or ""
    pr_file_path = None
    diffs = get_pr_diffs(repo, pr)
    pr_line = None

    issue_number = re.search(r"Fixes #(?P<issue_number>\d+).", pr_body).group(
        "issue_number"
    )
    author = repo.get_issue(int(issue_number)).user.login
    logger.info(f"Author of original issue is {author}")
    chat_logger = (
        chat_logger
        if chat_logger is not None
        else ChatLogger(
            {
                "repo_name": repo_name,
                "title": "(Comment) " + pr_title,
                "issue_url": pr.html_url,
                "pr_file_path": pr_file_path,  # may be None
                "pr_line": pr_line,  # may be None
                "repo_full_name": repo_full_name,
                "repo_description": repo_description,
                "comment": comment,
                "pr_path": pr_path,
                "pr_line_position": pr_line_position,
                "username": author,
                "installation_id": installation_id,
                "pr_number": pr_number,
                "type": "comment",
            }
        )
    )

    is_paying_user = chat_logger.is_paying_user()
    use_faster_model = chat_logger.use_faster_model(g)

    metadata = construct_metadata(
        repo_full_name,
        repo_name,
        organization,
        repo_description,
        installation_id,
        username,
        "on_comment",
        "gpt-3.5" if use_faster_model else "gpt-4",
        "pro" if is_paying_user else "free",
        PREFIX,
    )

    capture_posthog_event(username, "started", properties=metadata)
    logger.info(f"Getting repo {repo_full_name}")
    file_comment = bool(pr_path) and bool(pr_line_position)

    item_to_react_to = None
    reaction = None

    try:
        # Check if the PR is closed
        if pr.state == "closed":
            return {"success": True, "message": "PR is closed. No event fired."}
        if comment_id:
            try:
                item_to_react_to = pr.get_issue_comment(comment_id)
                reaction = item_to_react_to.create_reaction("eyes")
            except Exception as e:
                try:
                    item_to_react_to = pr.get_review_comment(comment_id)
                    reaction = item_to_react_to.create_reaction("eyes")
                except Exception as e:
                    pass

            if reaction is not None:
                # Delete rocket reaction
                reactions = item_to_react_to.get_reactions()
                for r in reactions:
                    if r.content == "rocket" and r.user.login == GITHUB_BOT_USERNAME:
                        item_to_react_to.delete_reaction(r.id)

        branch_name = (
            pr.head.ref if pr_number else pr.pr_head  # pylint: disable=no-member
        )
        # This means it's a comment on a file
        if file_comment:
            pr_file = repo.get_contents(
                pr_path, ref=branch_name
            ).decoded_content.decode("utf-8")
            pr_lines = pr_file.splitlines()
            pr_line = pr_lines[min(len(pr_lines), pr_line_position) - 1]
            pr_file_path = pr_path.strip()

        def fetch_file_contents_with_retry():
            retries = 1
            error = None
            for i in range(retries):
                try:
                    logger.info(f"Fetching relevant files for the {i}th time...")
                    return search_snippets(
                        repo,
                        f"{comment}\n{pr_title}" + (f"\n{pr_line}" if pr_line else ""),
                        num_files=30,
                        branch=branch_name,
                        installation_id=installation_id,
                    )
                except Exception as e:
                    error = e
                    continue
            capture_posthog_event(
                username, "fetching_failed", properties={"error": error, **metadata}
            )
            raise error

        if file_comment:
            snippets = []
            tree = ""
        else:
            try:
                logger.info("Fetching relevant files...")
                snippets, tree = fetch_file_contents_with_retry()
                assert len(snippets) > 0
            except Exception as e:
                logger.error(traceback.format_exc())
                raise e

        snippets = post_process_snippets(
            snippets, max_num_of_snippets=0 if file_comment else 2
        )

        logger.info("Getting response from ChatGPT...")
        human_message = HumanMessageCommentPrompt(
            comment=comment,
            repo_name=repo_name,
            repo_description=repo_description if repo_description else "",
            diffs=diffs,
            issue_url=pr.html_url,
            username=username,
            title=pr_title,
            tree=tree,
            summary=pr_body,
            snippets=snippets,
            pr_file_path=pr_file_path,  # may be None
            pr_line=pr_line,  # may be None
        )
        logger.info(f"Human prompt{human_message.construct_prompt()}")

        sweep_bot = SweepBot.from_system_message_content(
            # human_message=human_message, model="claude-v1.3-100k", repo=repo
            human_message=human_message,
            repo=repo,
            chat_logger=chat_logger,
            model="gpt-3.5" if use_faster_model else "gpt-4-32k-0613",
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        capture_posthog_event(
            username,
            "failed",
            properties={"error": str(e), "reason": "Failed to get files", **metadata},
        )
        raise e

    try:
        logger.info("Fetching files to modify/create...")
        if file_comment:
            file_change_requests = [
                FileChangeRequest(
                    filename=pr_file_path,
                    instructions=f"{comment}\n\nCommented on this line: {pr_line}",
                    change_type="modify",
                )
            ]
        else:
            if comment.strip().lower().startswith("sweep: regenerate"):
                logger.info("Running regenerate...")

                file_paths = comment.strip().split(" ")[2:]

                def get_contents_with_fallback(repo: Repository, file_path: str):
                    try:
                        return repo.get_contents(file_path)
                    except Exception as e:
                        logger.error(e)
                        return None

                old_file_contents = [
                    get_contents_with_fallback(repo, file_path)
                    for file_path in file_paths
                ]
                print(old_file_contents)
                for file_path, old_file_content in zip(file_paths, old_file_contents):
                    current_content = sweep_bot.get_contents(
                        file_path, branch=branch_name
                    )
                    if old_file_content:
                        logger.info("Resetting file...")
                        sweep_bot.repo.update_file(
                            file_path,
                            f"Reset {file_path}",
                            old_file_content.decoded_content,
                            sha=current_content.sha,
                            branch=branch_name,
                        )
                    else:
                        logger.info("Deleting file...")
                        sweep_bot.repo.delete_file(
                            file_path,
                            f"Reset {file_path}",
                            sha=current_content.sha,
                            branch=branch_name,
                        )

                quoted_pr_summary = "> " + pr.body.replace("\n", "\n> ")
                file_change_requests = [
                    FileChangeRequest(
                        filename=file_path,
                        instructions=f"Modify the file {file_path} based on the PR summary:\n\n{quoted_pr_summary}",
                        change_type="modify",
                    )
                    for file_path in file_paths
                ]
                print(file_change_requests)
                file_change_requests = sweep_bot.validate_file_change_requests(
                    file_change_requests, branch=branch_name
                )

                logger.info("Getting response from ChatGPT...")
                human_message = HumanMessageCommentPrompt(
                    comment=comment,
                    repo_name=repo_name,
                    repo_description=repo_description if repo_description else "",
                    diffs=get_pr_diffs(repo, pr),
                    issue_url=pr.html_url,
                    username=username,
                    title=pr_title,
                    tree=tree,
                    summary=pr_body,
                    snippets=snippets,
                    pr_file_path=pr_file_path,  # may be None
                    pr_line=pr_line,  # may be None
                )

                logger.info(f"Human prompt{human_message.construct_prompt()}")
                sweep_bot = SweepBot.from_system_message_content(
                    human_message=human_message,
                    repo=repo,
                    chat_logger=chat_logger,
                )
            else:
                file_change_requests, _ = sweep_bot.get_files_to_change(retries=3)
                file_change_requests = sweep_bot.validate_file_change_requests(
                    file_change_requests, branch=branch_name
                )

            sweep_response = "I couldn't find any relevant files to change."
            if file_change_requests:
                table_message = tabulate(
                    [
                        [
                            f"`{file_change_request.filename}`",
                            file_change_request.instructions_display.replace(
                                "\n", "<br/>"
                            ).replace("```", "\\```"),
                        ]
                        for file_change_request in file_change_requests
                    ],
                    headers=["File Path", "Proposed Changes"],
                    tablefmt="pipe",
                )
                sweep_response = (
                    f"I decided to make the following changes:\n\n{table_message}"
                )
            quoted_comment = "> " + comment.replace("\n", "\n> ")
            response_for_user = (
                f"{quoted_comment}\n\nHi @{username},\n\n{sweep_response}"
            )
            if pr_number:
                pr.create_issue_comment(response_for_user)
        logger.info("Making Code Changes...")

        blocked_dirs = get_blocked_dirs(sweep_bot.repo)

        list(
            sweep_bot.change_files_in_github_iterator(
                file_change_requests, branch_name, blocked_dirs
            )
        )
        if type(pr) != MockPR:
            if pr.user.login == GITHUB_BOT_USERNAME and pr.title.startswith("[DRAFT] "):
                # Update the PR title to remove the "[DRAFT]" prefix
                pr.edit(title=pr.title.replace("[DRAFT] ", "", 1))

        logger.info("Done!")
    except NoFilesException:
        capture_posthog_event(
            username,
            "failed",
            properties={
                "error": "No files to change",
                "reason": "No files to change",
                **metadata,
            },
        )
        return {"success": True, "message": "No files to change."}
    except Exception as e:
        logger.error(traceback.format_exc())
        capture_posthog_event(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Failed to make changes",
                **metadata,
            },
        )
        raise e

    # Delete eyes
    if reaction is not None:
        item_to_react_to.delete_reaction(reaction.id)

    try:
        item_to_react_to = pr.get_issue_comment(comment_id)
        reaction = item_to_react_to.create_reaction("rocket")
    except Exception as e:
        try:
            item_to_react_to = pr.get_review_comment(comment_id)
            reaction = item_to_react_to.create_reaction("rocket")
        except Exception as e:
            pass

    capture_posthog_event(username, "success", properties={**metadata})
    logger.info("on_comment success")
    return {"success": True}


def capture_posthog_event(username, event, properties):
    posthog.capture(username, event, properties=properties)


def rollback_file(repo_full_name, pr_path, installation_id, pr_number):
    _, g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)
    branch_name = pr.head.ref

    # Get the file's content from the previous commit
    commits = repo.get_commits(sha=branch_name)
    if commits.totalCount < 2:
        current_file = repo.get_contents(pr_path, ref=commits[0].sha)
        current_file_sha = current_file.sha
        previous_content = repo.get_contents(pr_path, ref=repo.default_branch)
        previous_file_content = previous_content.decoded_content.decode("utf-8")
        repo.update_file(
            pr_path,
            "Revert file to previous commit",
            previous_file_content,
            current_file_sha,
            branch=branch_name,
        )
        return
    previous_commit = commits[1]

    # Get current file SHA
    current_file = repo.get_contents(pr_path, ref=commits[0].sha)
    current_file_sha = current_file.sha

    # Check if the file exists in the previous commit
    try:
        previous_content = repo.get_contents(pr_path, ref=previous_commit.sha)
        previous_file_content = previous_content.decoded_content.decode("utf-8")
        # Create a new commit with the previous file content
        repo.update_file(
            pr_path,
            "Revert file to previous commit",
            previous_file_content,
            current_file_sha,
            branch=branch_name,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        if e.status == 404:  # pylint: disable=no-member
            logger.warning(
                f"File {pr_path} was not found in previous commit {previous_commit.sha}"
            )
        else:
            raise e
