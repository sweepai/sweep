import re
import traceback

import openai
from logn import logger, LogTask

from typing import Any
from tabulate import tabulate
from github.Repository import Repository

from sweepai.config.client import get_blocked_dirs
from sweepai.core.entities import (
    NoFilesException,
    Snippet,
    MockPR,
    FileChangeRequest,
    SweepContext,
)
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs
from sweepai.utils.chat_logger import ChatLogger
from sweepai.config.server import (
    GITHUB_BOT_USERNAME,
    ENV,
    MONGODB_URI,
    OPENAI_API_KEY,
)
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.search_utils import search_snippets
from sweepai.utils.prompt_constructor import HumanMessageCommentPrompt

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


@LogTask()
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
    pr_body = pr.body or ""
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
        token=None,  # Todo(lukejagg): Make this token for sandbox on comments
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

    capture_posthog_event(username, "started", properties=metadata)
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
            except Exception as e:
                try:
                    item_to_react_to = pr.get_review_comment(comment_id)
                    reaction = item_to_react_to.create_reaction("eyes")
                except SystemExit:
                    raise SystemExit
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
        cloned_repo = ClonedRepo(repo_full_name, installation_id, branch=branch_name)
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
                + f"\n{pr_lines[pr_line_position - 1]} <<<< COMMENT: {comment} <<<<"
                + "\n".join(pr_lines[pr_line_position:end])
            )
            if comment_id:
                bot_comment = pr.create_review_comment_reply(
                    comment_id, "Working on it..."
                )
        else:
            formatted_pr_chunk = None  # pr_file
            bot_comment = pr.create_issue_comment("Working on it...")
        if file_comment:
            snippets = []
            tree = ""
        else:
            try:
                logger.info("Fetching relevant files...")
                snippets, tree = search_snippets(
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
            pr_chunk=formatted_pr_chunk,  # may be None
            original_line=original_line if pr_chunk else None,
        )
        logger.info(f"Human prompt{human_message.construct_prompt()}")

        sweep_bot = SweepBot.from_system_message_content(
            # human_message=human_message, model="claude-v1.3-100k", repo=repo
            human_message=human_message,
            repo=repo,
            chat_logger=chat_logger,
            model="gpt-3.5-turbo-16k-0613" if use_faster_model else "gpt-4-32k-0613",
            sweep_context=sweep_context,
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        capture_posthog_event(
            username,
            "failed",
            properties={"error": str(e), "reason": "Failed to get files", **metadata},
        )
        edit_comment(ERROR_FORMAT.format(title="Failed to get files"))
        raise e

    try:
        logger.info("Fetching files to modify/create...")
        if file_comment:
            file_change_requests = [
                FileChangeRequest(
                    filename=pr_file_path,
                    instructions=f"The user left a comment in this chunk of code:\n<review_code_chunk>{formatted_pr_chunk}\n</review_code_chunk>\n. Resolve their comment.",
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
                file_change_requests = []
                if original_issue:
                    content = original_issue.body
                    checklist_dropdown = re.search(
                        "<details>\n<summary>Checklist</summary>.*?</details>",
                        content,
                        re.DOTALL,
                    )
                    checklist = checklist_dropdown.group(0)
                    matches = re.findall(
                        (
                            "- \[[X ]\] `(?P<filename>.*?)`(?P<instructions>.*?)(?=-"
                            " \[[X ]\]|</details>)"
                        ),
                        checklist,
                        re.DOTALL,
                    )
                    instructions_mapping = {}
                    for filename, instructions in matches:
                        instructions_mapping[filename] = instructions
                    file_change_requests = [
                        FileChangeRequest(
                            filename=file_path,
                            instructions=instructions_mapping[file_path],
                            change_type="modify",
                        )
                        for file_path in file_paths
                    ]
                else:
                    quoted_pr_summary = "> " + pr.body.replace("\n", "\n> ")
                    file_change_requests = [
                        FileChangeRequest(
                            filename=file_path,
                            instructions=(
                                f"Modify the file {file_path} based on the PR"
                                f" summary:\n\n{quoted_pr_summary}"
                            ),
                            change_type="modify",
                        )
                        for file_path in file_paths
                    ]
                logger.print(file_change_requests)
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
                    pr_chunk=pr_chunk,  # may be None
                    original_line=original_line if pr_chunk else None,
                )

                logger.info(f"Human prompt{human_message.construct_prompt()}")
                sweep_bot = SweepBot.from_system_message_content(
                    human_message=human_message,
                    repo=repo,
                    chat_logger=chat_logger,
                )
            else:
                file_change_requests, _ = sweep_bot.get_files_to_change(retries=1)
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
        capture_posthog_event(
            username,
            "failed",
            properties={
                "error": "No files to change",
                "reason": "No files to change",
                **metadata,
            },
        )
        edit_comment(ERROR_FORMAT.format(title="Could not find files to change"))
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
    except Exception as e:
        try:
            item_to_react_to = pr.get_review_comment(comment_id)
            reaction = item_to_react_to.create_reaction("rocket")
        except SystemExit:
            raise SystemExit
        except Exception as e:
            pass

    try:
        if response_for_user is not None:
            edit_comment(f"## 🚀 Wrote Changes\n\n{response_for_user}")
    except SystemExit:
        raise SystemExit
    except Exception as e:
        pass

    capture_posthog_event(username, "success", properties={**metadata})
    logger.info("on_comment success")
    return {"success": True}


def capture_posthog_event(username, event, properties):
    posthog.capture(username, event, properties=properties)
