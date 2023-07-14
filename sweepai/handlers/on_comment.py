import traceback

import openai
from loguru import logger

from sweepai.core.entities import NoFilesException, Snippet
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.config.server import PREFIX, OPENAI_API_KEY, GITHUB_BOT_TOKEN
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
):
    # Check if the comment is "REVERT"
    if comment.strip().upper() == "REVERT":
        rollback_file(repo_full_name, pr_path, installation_id, pr_number)
        return {"success": True, "message": "File has been reverted to the previous commit."}

    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR
    logger.info(
        f"Calling on_comment() with the following arguments: {comment}, {repo_full_name}, {repo_description}, {pr_path}")
    organization, repo_name = repo_full_name.split("/")
    metadata = {
        "repo_full_name": repo_full_name,
        "repo_name": repo_name,
        "organization": organization,
        "repo_description": repo_description,
        "installation_id": installation_id,
        "username": username,
        "function": "on_comment",
        "mode": PREFIX,
    }

    posthog.capture(username, "started", properties=metadata)
    logger.info(f"Getting repo {repo_full_name}")
    file_comment = pr_path and pr_line_position
    try:
        g = get_github_client(installation_id)
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        # Check if the PR is closed
        if pr.state == "closed":
            return {"success": True, "message": "PR is closed. No event fired."}
        branch_name = pr.head.ref
        pr_title = pr.title
        pr_body = pr.body
        diffs = get_pr_diffs(repo, pr)
        pr_line = None
        pr_file_path = None
        # This means it's a comment on a file
        if file_comment:
            pr_file = repo.get_contents(pr_path, ref=branch_name).decoded_content.decode("utf-8")
            pr_lines = pr_file.splitlines()
            pr_line = pr_lines[min(len(pr_lines), pr_line_position) - 1]
            pr_file_path = pr_path.strip()
        # This means it's a comment on the PR
        else:
            if not comment.strip().lower().startswith("sweep"):
                logger.info("No event fired because it doesn't start with Sweep.")
                return {"success": True, "message": "No event fired."}
        try:
            comments = list(pr.get_issue_comments())
            if len(comments) > 0:
                comment_id = comments[-1].id
        except Exception as e:
            logger.error(f"Failed to fetch comments: {str(e)}")
            return {"success": False, "message": "Failed to fetch comments from the pull request."}
        pr = repo.get_pull(pr_number)
        try:
            comments = list(pr.get_issue_comments())
            if len(comments) > 0:
                comment_id = comments[-1].id
        except Exception as e:
            logger.error(f"Failed to fetch comments: {str(e)}")
            return {"success": False, "message": "Failed to fetch comments from the pull request."}
        repo = g.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        # Check if the PR is closed
        if pr.state == "closed":
            return {"success": True, "message": "PR is closed. No event fired."}
        branch_name = pr.head.ref
        pr_title = pr.title
        pr_body = pr.body
        diffs = get_pr_diffs(repo, pr)
        pr_line = None
        pr_file_path = None
        # This means it's a comment on a file
        if file_comment:
            pr_file = repo.get_contents(pr_path, ref=branch_name).decoded_content.decode("utf-8")
            pr_lines = pr_file.splitlines()
            pr_line = pr_lines[min(len(pr_lines), pr_line_position) - 1]
            pr_file_path = pr_path.strip()
        # This means it's a comment on the PR
        else:
            if not comment.strip().lower().startswith("sweep"):
                logger.info("No event fired because it doesn't start with Sweep.")
                return {"success": True, "message": "No event fired."}

        def fetch_file_contents_with_retry():
            retries = 3
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
            posthog.capture(
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
        chat_logger = ChatLogger({
            'repo_name': repo_name,
            'title': '(Comment) ' + pr_title,
            "issue_url": pr.html_url,
            "pr_file_path": pr_file_path,  # may be None
            "pr_line": pr_line,  # may be None
            "repo_full_name": repo_full_name,
            "repo_description": repo_description,
            "comment": comment,
            "pr_path": pr_path,
            "pr_line_position": pr_line_position,
            "username": username,
            "installation_id": installation_id,
            "pr_number": pr_number,
            "type": "comment",
        })
        snippets = post_process_snippets(snippets, max_num_of_snippets=0 if file_comment else 2)

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
            human_message=human_message, repo=repo, chat_logger=chat_logger, model="gpt-4-32k-0613"
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        posthog.capture(username, "failed", properties={
            "error": str(e),
            "reason": "Failed to get files",
            **metadata
        })
        raise e

    try:
        logger.info("Fetching files to modify/create...")
        file_change_requests = sweep_bot.get_files_to_change(retries=3)
        file_change_requests = sweep_bot.validate_file_change_requests(file_change_requests, branch=branch_name)
        logger.info("Making Code Changes...")
        sweep_bot.change_files_in_github(file_change_requests, branch_name)

        logger.info("Done!")
    except NoFilesException:
        posthog.capture(username, "failed", properties={
            "error": "No files to change",
            "reason": "No files to change",
            **metadata
        })
        return {"success": True, "message": "No files to change."}
    except Exception as e:
        logger.error(traceback.format_exc())
        posthog.capture(username, "failed", properties={
            "error": str(e),
            "reason": "Failed to make changes",
            **metadata
        })
        raise e

    posthog.capture(username, "success", properties={**metadata})
    if comment_id:
        item_to_react_to = pr.get_issue_comment(comment_id)
        item_to_react_to.create_reaction("eyes")
    return {"success": True}
