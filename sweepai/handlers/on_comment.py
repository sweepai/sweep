"""
on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py.
It is also called in sweepai/handlers/on_ticket.py when Sweep is reviewing its own PRs.
"""
import re
import time
import traceback
from typing import Any

import openai
from github.Repository import Repository
from tabulate import tabulate

from sweepai.logn import logger
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
    logger.info(
        f"Calling on_comment() with the following arguments: {comment},"
        f" {repo_full_name}, {repo_description}, {pr_path}"
    )
    organization, repo_name = repo_full_name.split("/")
    start_time = time.time()

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

    elapsed_time = time.time() - start_time
    posthog.capture(username, "started", properties={**metadata, "duration": elapsed_time})
    logger.info(f"Getting repo {repo_full_name}")
    file_comment = bool(pr_path) and bool(pr_line_position)

    item_to_react_to = None
    reaction = None

    bot_comment = None

    def edit_comment(new_comment):
        if bot_comment is not None:
            bot_comment.edit(new_comment)

    try:
        # Check if the PR is closed
        if pr.state == "closed":
            return {"success": True, "message": "PR is closed. No event fired."}
        if comment_id:
            try:
                item_to_react_to = pr.get_issue_comment(comment_id)
                reaction = item_to_react_to.create_reaction("eyes")
            except SystemExit:
                raise SystemExit
            except Exception:
                try:
                    item_to_react_to = pr.get_review_comment(comment_id)
                    reaction = item_to_react_to.create_reaction("eyes")
                except SystemExit:
                    raise SystemExit
                except Exception:
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
        cloned_repo = ClonedRepo(repo_full_name, installation_id, branch=branch_name)

        # Generate diffs for this PR
        pr_diff_string = None
        pr_files_modified = None
        if pr_number:
            patches = []
            pr_files_modified = {}
            files = pr.get_files()
            for file in files:
                if file.status == "modified":
                    # Get the entire file contents, not just the patch
                    pr_files_modified[file.filename] = repo.get_contents(
                        file.filename, ref=branch_name
                    ).decoded_content.decode("utf-8")

                    patches.append(
                        f'<file file_path="{file.filename}">\n{file.patch}\n</file>'
                    )
            pr_diff_string = (
                "<files_changed>\n" + "\n".join(patches) + "\n</files_changed>"
            )

        # This means it's a comment on a file
        if file_comment:
            pr_file = repo.get_contents(
                pr_path, ref=branch_name
            ).decoded_content.decode("utf-8")
            pr_lines = pr_file.splitlines()
            start = max(0, pr_line_position - 11)
            end = min(len(pr_lines), pr_line_position + 10)
            original_line = pr_lines[pr_line_position - 1]
            pr_chunk = "\n".join(pr_lines[start:end])
            pr_file_path = pr_path.strip()
            formatted_pr_chunk = (
                "\n".join(pr_lines[start : pr_line_position - 1])
                + f"\n{pr_lines[pr_line_position - 1]} <<<< COMMENT: {comment.strip()} <<<<\n"
                + "\n".join(pr_lines[pr_line_position:end])
            )
            if comment_id:
                try:
                    bot_comment = pr.create_review_comment_reply(
                        comment_id, "Working on it..."
                    )
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    print(e)
        else:
            formatted_pr_chunk = None  # pr_file
            bot_comment = pr.create_issue_comment("Working on it...")
        if file_comment:
            snippets = []
            tree = ""
        else:
            try:
                logger.info("Fetching relevant files...")
                snippets, tree, _ = search_snippets(
                    cloned_repo,
                    f"{comment}\n{pr_title}" + (f"\n{pr_chunk}" if pr_chunk else ""),
                    num_files=30,
                )
                assert len(snippets) > 0
            except Exception as e:
                logger.error(traceback.format_exc())
                raise e

        snippets = post_process_snippets(
            snippets, max_num_of_snippets=0 if file_comment else 2
        )
        commit_history = cloned_repo.get_commit_history(username=username)
        user_dict = get_documentation_dict(repo)
        docs_results = extract_relevant_docs(
                pr_title + "\n" + pr_body + "\n" + f" User Comment: {comment}", user_dict, chat_logger
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
            commit_history=commit_history,
            pr_file_path=pr_file_path,  # may be None
            pr_chunk=formatted_pr_chunk,  # may be None
            original_line=original_line if pr_chunk else None,
            relevant_docs=docs_results,
        )
        logger.info(f"Human prompt{human_message.construct_prompt()}")

        sweep_bot = SweepBot.from_system_message_content(
            # human_message=human_message, model="claude-v1.3-100k", repo=repo
            human_message=human_message,
            repo=repo,
            chat_logger=chat_logger,
            model="gpt-4-32k-0613" if use_faster_model else "gpt-4-32k-0613",
            sweep_context=sweep_context,
            cloned_repo=cloned_repo,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        elapsed_time = time.time() - start_time
        posthog.capture(
            username,
            "failed",
            properties={"error": str(e), "reason": "Failed to get files", "duration": elapsed_time, **metadata},
        )
        edit_comment(ERROR_FORMAT.format(title="Failed to get files"))
        raise e

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
                f"I am making the following changes:\n\n{table_message}"
            )
        quoted_comment = "> " + comment.replace("\n", "\n> ")
        response_for_user = (
            f"{quoted_comment}\n\nHi @{username},\n\n{sweep_response}"
        )
        if pr_number:
            edit_comment(response_for_user)

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
                    response_for_user = ("Done.")
                else:
                    response_for_user = (
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
        elapsed_time = time.time() - start_time
        posthog.capture(
            username,
            "failed",
            properties={
                "error": "No files to change",
                "reason": "No files to change",
                "duration": elapsed_time,
                **metadata,
            },
        )
        edit_comment(ERROR_FORMAT.format(title="Could not find files to change"))
        return {"success": True, "message": "No files to change."}
    except Exception as e:
        logger.error(traceback.format_exc())
        elapsed_time = time.time() - start_time
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Failed to make changes",
                "duration": elapsed_time,
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

    elapsed_time = time.time() - start_time
    posthog.capture(username, "success", properties={**metadata, "duration": elapsed_time})
    logger.info("on_comment success")
    return {"success": True}
