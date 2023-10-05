"""
on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py.
It is also called in sweepai/handlers/on_ticket.py when Sweep is reviewing its own PRs.
"""
import re
import traceback
from typing import Any

import openai
from github.Repository import Repository
from tabulate import tabulate

from logn import LogTask, logger
from sweepai.config.client import get_blocked_dirs, get_documentation_dict
from sweepai.config.server import ENV, GITHUB_BOT_USERNAME, MONGODB_URI, OPENAI_API_KEY
from sweepai.core.documentation_searcher import extract_relevant_docs
from sweepai.core.entities import (
    FileChangeRequest,
    MockPR,
    NoFilesException,
    Snippet,
    SweepContext,
)
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.prompt_constructor import HumanMessageCommentPrompt
from sweepai.utils.search_utils import search_snippets

openai.api_key = OPENAI_API_KEY

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2
num_extended_snippets = 2

ERROR_FORMAT = "❌ {title}\n\nPlease join our [Discord](https://discord.gg/sweep) to report this issue."


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


# @LogTask()
import time
start_time = time.time()
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
    chat_logger: Any = None,
    pr: MockPR = None,  # For on_comment calls before PR is created
    repo: Any = None,
    comment_type: str = "comment",
    type: str = "comment",
):
    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR
    logger.info(
        f"Calling on_comment() with the following arguments: {comment},"
        f" {repo_full_name}, {repo_description}, {pr_path}"
    )
    organization, repo_name = repo_full_name.split("/")

    _token, g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    if pr is None:
        pr = repo.get_pull(pr_number)
    pr_title = pr.title
    pr_body = pr.body.split("🎉 Latest improvements to Sweep:")[0] if pr.body and "🎉 Latest improvements to Sweep:" in pr.body else pr.body
    pr_file_path = None
    diffs = get_pr_diffs(repo, pr)
    pr_chunk = None
    formatted_pr_chunk = None

    issue_number_match = re.search(r"Fixes #(?P<issue_number>\d+).", pr_body)
    original_issue = None
    if issue_number_match:
        issue_number = issue_number_match.group("issue_number")
        original_issue = repo.get_issue(int(issue_number))
        author = original_issue.user.login
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
                    "pr_chunk": pr_chunk,  # may be None
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
            if MONGODB_URI
            else None
        )
    else:
        logger.warning(f"No issue number found in PR body for summary {pr.body}")
        chat_logger = None

    if chat_logger:
        is_paying_user = chat_logger.is_paying_user()
        use_faster_model = chat_logger.use_faster_model(g)
    else:
        # Todo: chat_logger is None for MockPRs, which will cause all comments to use GPT-4
        is_paying_user = True
        use_faster_model = False

    assignee = pr.assignee.login if pr.assignee else None

    sweep_context = SweepContext.create(
        username=username,
        issue_url=pr.html_url,
        use_faster_model=use_faster_model,
        is_paying_user=is_paying_user,
        repo=repo,
        token=_token,
    )

    metadata = {
        "repo_full_name": repo_full_name,
        "repo_name": repo_name,
        "organization": organization,
        "repo_description": repo_description,
        "installation_id": installation_id,
        "username": username if not username.startswith("sweep") else assignee,
        "function": "on_comment",
        "model": "gpt-3.5" if use_faster_model else "gpt-4",
        "tier": "pro" if is_paying_user else "free",
        "mode": ENV,
        "pr_path": pr_path,
        "pr_line_position": pr_line_position,
        "pr_number": pr_number or pr.id,
        "pr_html_url": pr.html_url,
        "comment_id": comment_id,
        "comment": comment,
        "issue_number": issue_number if issue_number_match else "",
    }
    # logger.bind(**metadata)

    duration = time.time() - start_time
    posthog.capture(username, "started", properties={"duration": duration, **metadata})

    try:
        logger.info("Fetching files to modify/create...")
        if file_comment:
            file_change_requests = [
                FileChangeRequest(
                    filename=pr_file_path,
                    instructions=f"The user left a comment in this chunk of code:\n<review_code_chunk>{formatted_pr_chunk}\n</review_code_chunk>.\nResolve their comment.",
                    change_type="modify",
                )
            ]
        else:
            regenerate = comment.strip().lower().startswith("sweep: regenerate")
            reset = comment.strip().lower().startswith("sweep: reset")
            if regenerate or reset:
                logger.info(f"Running {'regenerate' if regenerate else 'reset'}...")

                file_paths = comment.strip().split(" ")[2:]

                def get_contents_with_fallback(repo: Repository, file_path: str):
                    try:
                        return repo.get_contents(file_path)
                    except SystemExit:
                        raise SystemExit
                    except Exception as e:
                        logger.error(e)
                        return None

                old_file_contents = [
                    get_contents_with_fallback(repo, file_path)
                    for file_path in file_paths
                ]

                logger.print(old_file_contents)
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
                if reset:
                    return {
                        "success": True,
                        "message": "Files have been reset to their original state.",
                    }
                return {
                    "success": True,
                    "message": "Files have been regenerated.",
                }
            else:
                non_python_count = sum(
                    not file_path.endswith(".py")
                    for file_path in human_message.get_file_paths()
                )
                python_count = len(human_message.get_file_paths()) - non_python_count
                is_python_issue = python_count > non_python_count
                file_change_requests, _ = sweep_bot.get_files_to_change(
                    is_python_issue, retries=1, pr_diffs=pr_diff_string
                )
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
                edit_comment(response_for_user)
                # pr.create_issue_comment(response_for_user)
        logger.info("Making Code Changes...")

        blocked_dirs = get_blocked_dirs(sweep_bot.repo)

        sweep_bot.comment_pr_diff_str = pr_diff_string
        sweep_bot.comment_pr_files_modified = pr_files_modified
        changes_made = sum(
            [
                change_made
                for _, change_made, _, _ in sweep_bot.change_files_in_github_iterator(
                    file_change_requests, branch_name, blocked_dirs
                )
            ]
        )
        try:
            if comment_id:
                if changes_made:
                    # PR Review Comment Reply
                    edit_comment("Done.")
                else:
                    # PR Review Comment Reply
                    edit_comment(
                        'I wasn\'t able to make changes. This could be due to an unclear request or a bug in my code.\n As a reminder, comments on a file only modify that file. Comments on a PR(at the bottom of the "conversation" tab) can modify the entire PR. Please try again or contact us on [Discord](https://discord.com/invite/sweep)'
                    )
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(f"Failed to reply to comment: {e}")

        if not isinstance(pr, MockPR):
            if pr.user.login == GITHUB_BOT_USERNAME and pr.title.startswith("[DRAFT] "):
                # Update the PR title to remove the "[DRAFT]" prefix
                pr.edit(title=pr.title.replace("[DRAFT] ", "", 1))

        logger.info("Done!")
    except NoFilesException:
        duration = time.time() - start_time
        posthog.capture(
            username,
            "failed",
            properties={
                "duration": duration,
                "error": "No files to change",
                "reason": "No files to change",
                **metadata,
            },
        )
        edit_comment(ERROR_FORMAT.format(title="Could not find files to change"))
        return {"success": True, "message": "No files to change."}
    except Exception as e:
        logger.error(traceback.format_exc())
        duration = time.time() - start_time
        posthog.capture(
            username,
            "failed",
            properties={
                "duration": duration,
                "error": str(e),
                "reason": "Failed to make changes",
                **metadata,
            },
        )
        edit_comment(ERROR_FORMAT.format(title="Failed to make changes"))
        raise e

    # Delete eyes
    if reaction is not None:
        item_to_react_to.delete_reaction(reaction.id)

    try:
        item_to_react_to = pr.get_issue_comment(comment_id)
        reaction = item_to_react_to.create_reaction("rocket")
    except SystemExit:
        raise SystemExit
    except Exception:
        try:
            item_to_react_to = pr.get_review_comment(comment_id)
            reaction = item_to_react_to.create_reaction("rocket")
        except SystemExit:
            raise SystemExit
        except Exception:
            pass

    try:
        if response_for_user is not None:
            edit_comment(f"## 🚀 Wrote Changes\n\n{response_for_user}")
    except SystemExit:
        raise SystemExit
    except Exception:
        pass

    duration = time.time() - start_time
    posthog.capture(username, "success", properties={"duration": duration, **metadata})
    logger.info("on_comment success")
    return {"success": True}
