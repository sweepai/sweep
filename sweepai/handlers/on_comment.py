"""
on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py.
It is also called in sweepai/handlers/on_ticket.py when Sweep is reviewing its own PRs.
"""
import copy
import re
import time
import traceback
from typing import Any

from loguru import logger

from sentry_sdk import set_user
from sweepai.chat.api import posthog_trace
from sweepai.config.server import (
    ENV,
    GITHUB_BOT_USERNAME,
    MONGODB_URI,
)
from sweepai.core.entities import MockPR, NoFilesException, Snippet, render_fcrs
from sweepai.core.pull_request_bot import PRSummaryBot
from sweepai.core.sweep_bot import get_files_to_change_for_on_comment
from sweepai.agents.modify_utils import set_fcr_change_type
from sweepai.handlers.create_pr import handle_file_change_requests
from sweepai.core.review_utils import format_pr_info, get_pr_changes, smart_prune_file_based_on_patches
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.concurrency_utils import fire_and_forget_wrapper
from sweepai.utils.diff import generate_diff
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, commit_multi_file_changes, get_github_client, sanitize_string_for_github, validate_and_sanitize_multi_file_changes
from sweepai.utils.str_utils import BOT_SUFFIX, FASTER_MODEL_MESSAGE, add_line_numbers, blockquote
from sweepai.utils.ticket_rendering_utils import center, sweeping_gif
from sweepai.utils.ticket_utils import prep_snippets

from github.Repository import Repository
from github.PullRequest import PullRequest

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2
num_extended_snippets = 2

ERROR_FORMAT = "❌ {title}\n\nPlease report this on our [community forum](https://community.sweep.dev/)."
SWEEPING_GIF = f"{center(sweeping_gif)}\n\n<div align='center'><h3>Sweep is working on resolving your comment...<h3/></div>\n\n"

@posthog_trace
def on_comment(
    username: str,
    repo_full_name: str,
    repo_description: str,
    comment: str,
    pr_path: str | None,
    pr_line_position: int | None,
    installation_id: int,
    pr_number: int = None,
    comment_id: int | None = None,
    chat_logger: Any = None,
    pr: MockPR = None,  # For on_comment calls before PR is created
    repo: Any = None,
    comment_type: str = "comment",
    type: str = "comment",
    tracking_id: str = None,
):
    set_user({"username": username})
    with logger.contextualize(
        tracking_id=tracking_id,
    ):
        # Initialization logic start
        logger.info(
            f"Calling on_comment() with the following arguments: {comment},"
            f" {repo_full_name}, {repo_description}, {pr_path}"
        )
        organization, repo_name = repo_full_name.split("/")
        start_time = time.time()
        _token, g = get_github_client(installation_id)
        repo: Repository = g.get_repo(repo_full_name)
        if pr is None:
            pr: PullRequest = repo.get_pull(pr_number)
        pr_title = pr.title
        pr_body = (
            pr.body.split("<details>\n<summary><b>🎉 Latest improvements to Sweep:")[0]
            if pr.body
            and "<details>\n<summary><b>🎉 Latest improvements to Sweep:" in pr.body
            else pr.body
        )
        pr_file_path = None
        pr_chunk = None
        formatted_pr_chunk = None
        if pr.state == "closed":
            return {"success": True, "message": "PR is closed. No event fired."}
        # Initialization logic end

        # Payment logic start
        assignee = pr.assignee.login if pr.assignee else None
        issue_number_match = re.search(r"Fixes #(?P<issue_number>\d+).", pr_body or "")
        original_issue = None
        if issue_number_match or assignee:
            if issue_number_match:
                issue_number = issue_number_match.group("issue_number")
            if not assignee:
                original_issue = repo.get_issue(int(issue_number))
                author = original_issue.user.login
            else:
                author = assignee
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
                    },
                    active=True,
                )
                if MONGODB_URI
                else None
            )
        else:
            chat_logger = None

        if chat_logger:
            is_paying_user = chat_logger.is_paying_user()
            use_faster_model = chat_logger.use_faster_model()
        else:
            # Todo: chat_logger is None for MockPRs, which will cause all comments to use GPT-4
            is_paying_user = True
            use_faster_model = False
        
        if use_faster_model:
            raise Exception(FASTER_MODEL_MESSAGE)
        # Payment logic end

        # Telemetry logic start
        assignee = pr.assignee.login if pr.assignee else None

        metadata = {
            "repo_full_name": repo_full_name,
            "repo_name": repo_name,
            "organization": organization,
            "repo_description": repo_description,
            "installation_id": installation_id,
            "username": username if not username.startswith("sweep") else assignee,
            "function": "on_comment",
            "model": "gpt-4",
            "tier": "pro" if is_paying_user else "free",
            "mode": ENV,
            "pr_path": pr_path,
            "pr_line_position": pr_line_position,
            "pr_number": pr_number or pr.id,
            "pr_html_url": pr.html_url,
            "comment_id": comment_id,
            "comment": comment,
            "issue_number": issue_number if issue_number_match else "",
            "tracking_id": tracking_id,
        }

        logger.bind(**metadata)

        logger.info(f"Getting repo {repo_full_name}")
        # Telemetry logic end

        file_comment = bool(pr_path) and bool(pr_line_position)

        item_to_react_to = None
        reaction = None

        bot_comment = None

        def edit_comment(new_comment: str) -> None:
            new_comment = sanitize_string_for_github(new_comment)
            if bot_comment is not None:
                bot_comment.edit(new_comment + "\n" + BOT_SUFFIX)

        try:
            if comment_id:
                try:
                    item_to_react_to = pr.get_issue_comment(comment_id)
                    reaction = item_to_react_to.create_reaction("eyes")
                except Exception:
                    try:
                        item_to_react_to = pr.get_review_comment(comment_id)
                        reaction = item_to_react_to.create_reaction("eyes")
                    except Exception:
                        pass

                if reaction is not None:
                    # Delete rocket reaction
                    reactions = item_to_react_to.get_reactions()
                    for r in reactions:
                        if (
                            r.content == "rocket"
                            and r.user.login == GITHUB_BOT_USERNAME
                        ):
                            item_to_react_to.delete_reaction(r.id)

            branch_name = (
                pr.head.ref if pr_number else pr.pr_head  # pylint: disable=no-member
            )
            cloned_repo = ClonedRepo(
                repo_full_name,
                installation_id,
                branch=branch_name,
                repo=repo,
                token=_token,
            )

            # Generate diffs for this PR
            pr_diff_string = ""
            if pr_number:
                pr_changes, _dropped_files, _unsuitable_files = get_pr_changes(
                    repo, pr, cloned_repo
                )
                patches = []
                source_codes = []
                for file_name, pr_change in pr_changes.items():
                    if pr_change.status == "modified":
                        # Get the entire file contents, not just the patch
                        numbered_source_code = add_line_numbers(pr_change.new_code, start=1)
                        pruned_source_code = smart_prune_file_based_on_patches(numbered_source_code, pr_change.patches)
                        source_codes.append(f'<file_with_patches_applied file_name="{file_name}">\n{pruned_source_code}\n</file>')
                        patch_changes = [patch.changes for patch in pr_change.patches]
                        patch_annotations = pr_change.annotations
                        patches_with_annotations = [f'<patch index="{i}">\n{patch}\n</patch>\n<patch_description index="{i}">\n{patch_annotations[i]}\n<patch_description>' for i, patch in enumerate(patch_changes)]
                        patches_string = "\n".join(patches_with_annotations)
                        patches.append(
                            f'<patches file_name="{file_name}">\n{patches_string}\n</patches>'
                        )
                # create source code string
                source_code_string = (
                    "<code_files_with_patches_applied>\n" + "\n".join(source_codes) + "\n</code_files_with_patches_applied>"
                )
                pr_diff_string = (
                    "<pr_changes>\n" + "\n".join(patches) + "\n\n# Here is the current state of the codebase with the above patches applied:\n\n" + source_code_string + "</pr_changes>"
                )

            # This means it's a comment on a file
            if file_comment:
                pr_file = repo.get_contents(
                    pr_path, ref=branch_name
                ).decoded_content.decode("utf-8")
                # splitlines returns empty array if the string is empty, split(\n) returns ['']
                pr_lines = pr_file.split('\n')
                start = max(0, pr_line_position - 11)
                end = min(len(pr_lines), pr_line_position + 10)
                pr_chunk = "\n".join(pr_lines[start:end])
                pr_file_path = pr_path.strip()
                formatted_pr_chunk = (
                    "\n".join(pr_lines[start : pr_line_position - 1])
                    + f"\n{pr_lines[pr_line_position - 1]} <--- GITHUB COMMENT: {comment.strip()} --->\n"
                    + "\n".join(pr_lines[pr_line_position:end])
                )
                if comment_id:
                    bot_comment = pr.create_review_comment_reply(
                        comment_id, SWEEPING_GIF + "Searching for relevant snippets..." + BOT_SUFFIX
                    )
            else:
                formatted_pr_chunk = None  # pr_file
                bot_comment = pr.create_issue_comment(SWEEPING_GIF + "Searching for relevant snippets..." + BOT_SUFFIX)

            search_query = comment.strip("\n")
            formatted_query = comment.strip("\n")
            snippets = prep_snippets(
                cloned_repo, search_query, use_multi_query=False
            )

            pr_diffs, _dropped_files, _unsuitable_files = get_pr_changes(repo, pr, cloned_repo)
            snippets_modified = [Snippet.from_file(
                pr_diff, cloned_repo.get_file_contents(pr_diff)
            ) for pr_diff in pr_diffs]
            snippets = snippets_modified + snippets
            snippets = snippets[:num_of_snippets_to_query]
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.exception(e)
            elapsed_time = time.time() - start_time
            posthog.capture(
                username,
                "failed",
                properties={
                    "error": str(e),
                    "traceback": f"An error occured during the search! The stack trace is below:\n\n{stack_trace}",
                    "duration": elapsed_time,
                    "tracking_id": tracking_id,
                    **metadata,
                },
            )
            edit_comment(ERROR_FORMAT.format(title=f"An error occured!\n\nThe exception message is:{str(e)}\n\nThe stack trace is:{stack_trace}"))
            raise e

        try:
            logger.info("Fetching files to modify/create...")
            edit_comment(SWEEPING_GIF + "I just completed searching for relevant files, now I'm making changes...")
            if file_comment:
                formatted_query = f"The user left this GitHub PR Review comment in `{pr_path}`:\n<comment>\n{comment}\n</comment>\nThis was where they left their comment on the PR:\n<review_code_chunk>\n{formatted_pr_chunk}\n</review_code_chunk>.\n\nResolve their comment."
            pull_request_info = format_pr_info(pr)
            renames_dict, file_change_requests, plan = get_files_to_change_for_on_comment(
                relevant_snippets=snippets,
                read_only_snippets=[],
                problem_statement=formatted_query,
                repo_name=repo_name,
                pr_info=pull_request_info,
                pr_diffs=pr_diff_string,
                cloned_repo=cloned_repo,
            )
            set_fcr_change_type(file_change_requests, cloned_repo)

            assert file_change_requests, NoFilesException("I couldn't find any relevant files to change.")

            planning_markdown = render_fcrs(file_change_requests)
            sweep_response = f"I'm going to make the following changes:\n\n{planning_markdown}\n\nI'm currently validating these changes using parsers and linters to check for syntax errors and undefined variables..."

            quoted_comment = blockquote(comment) + "\n\n"
            response_for_user = (
                f"{quoted_comment}\n\nHi @{username},\n\n{sweep_response}"
            )
            edit_comment(SWEEPING_GIF + response_for_user)
            
            modify_files_dict, changes_made, file_change_requests = handle_file_change_requests(
                file_change_requests=file_change_requests,
                request=file_comment,
                cloned_repo=cloned_repo,
                username=username,
                installation_id=installation_id,
                renames_dict=renames_dict,
            )
            logger.info("\n".join(generate_diff(file_data["original_contents"], file_data["contents"]) for file_data in modify_files_dict.values()))
            pull_request_bot = PRSummaryBot()
            commit_message = pull_request_bot.get_commit_message(modify_files_dict, renames_dict=renames_dict, chat_logger=chat_logger)[:50]
            new_file_contents_to_commit = {file_path: file_data["contents"] for file_path, file_data in modify_files_dict.items()}
            previous_file_contents_to_commit = copy.deepcopy(new_file_contents_to_commit)
            new_file_contents_to_commit, files_removed = validate_and_sanitize_multi_file_changes(cloned_repo.repo, new_file_contents_to_commit, file_change_requests)
            if files_removed and username:
                posthog.capture(
                    username,
                    "polluted_commits_error",
                    properties={
                        "old_keys": ",".join(previous_file_contents_to_commit.keys()),
                        "new_keys": ",".join(new_file_contents_to_commit.keys()) 
                    },
                )
            commit = commit_multi_file_changes(cloned_repo, new_file_contents_to_commit, commit_message, branch_name)
            logger.info("Done!")
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(stack_trace)
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
            edit_comment(ERROR_FORMAT.format(title=f"Failed to make changes:\n\nThe exception message is:{str(e)}\n\nThe stack trace is:{stack_trace}"))
            raise e

        # Delete eyes
        if reaction is not None:
            item_to_react_to.delete_reaction(reaction.id)

        try:
            item_to_react_to = pr.get_issue_comment(comment_id)
            reaction = item_to_react_to.create_reaction("rocket")
        except Exception:
            try:
                item_to_react_to = pr.get_review_comment(comment_id)
                reaction = item_to_react_to.create_reaction("rocket")
            except Exception:
                pass

        patch_diff = ""
        for file_path, file_data in modify_files_dict.items():
            if file_path in new_file_contents_to_commit:
                patch_diff += f"--- {file_path}\n+++ {file_path}\n{generate_diff(file_data['original_contents'], file_data['contents'])}\n\n"
        
        if patch_diff:
            edit_comment(f"### 🚀 Resolved via [{commit.sha[:7]}](https://github.com/{repo_full_name}/commit/{commit.sha})\n\nHere were the changes I made:\n```diff\n{patch_diff}\n```")
        else:
            edit_comment(f"### 🚀 Resolved via [{commit.sha[:7]}](https://github.com/{repo_full_name}/commit/{commit.sha})")


        elapsed_time = time.time() - start_time
        # make async
        fire_and_forget_wrapper(posthog.capture)(
            username,
            "success",
            properties={
                **metadata,
                "tracking_id": tracking_id,
                "duration": elapsed_time,
            },
        )
        return {"success": True}
