"""
On Github ticket, get ChatGPT to deal with it
"""

# TODO: Add file validation

import os
import openai

from loguru import logger
import modal

from sweepai.core.entities import FileChangeRequest, Snippet
from sweepai.core.prompts import (
    reply_prompt,
)
from sweepai.core.sweep_bot import SweepBot
from sweepai.core.prompts import issue_comment_prompt
from sweepai.handlers.create_pr import create_pr
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client, search_snippets
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.constants import DB_NAME, PREFIX, UTILS_NAME

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

update_index = modal.Function.lookup(DB_NAME, "update_index")

bot_suffix = "I'm a bot that handles simple bugs and feature requests \
but I might make mistakes. Please be kind!"

collapsible_template = """
<details>
  <summary>{summary}</summary>

  {body}
</details>
"""

chunker = modal.Function.lookup(UTILS_NAME, "Chunking.chunk")

num_of_snippets_to_query = 30
max_num_of_snippets = 5

def on_ticket(
    title: str,
    summary: str,
    issue_number: int,
    issue_url: str,
    username: str,
    repo_full_name: str,
    repo_description: str,
    installation_id: int,
    comment_id: int = None
):
    # Check if the title starts with "sweep" or "sweep: " and remove it
    if title.lower().startswith("sweep: "):
        title = title[7:]
    elif title.lower().startswith("sweep "):
        title = title[6:]

    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR

    organization, repo_name = repo_full_name.split("/")
    metadata = {
        "issue_url": issue_url,
        "issue_number": issue_number,
        "repo_full_name": repo_full_name,
        "organization": organization,
        "repo_name": repo_name,
        "repo_description": repo_description,
        "username": username,
        "installation_id": installation_id,
        "function": "on_ticket",
        "mode": PREFIX,
    }
    posthog.capture(username, "started", properties=metadata)

    g = get_github_client(installation_id)

    if comment_id:
        logger.info(f"Replying to comment {comment_id}...")
    logger.info(f"Getting repo {repo_full_name}")
    repo = g.get_repo(repo_full_name)
    current_issue = repo.get_issue(number=issue_number)
    if current_issue.state == 'closed':
        posthog.capture(username, "issue_closed", properties=metadata)
        return {"success": False, "reason": "Issue is closed"}
    item_to_react_to = current_issue.get_comment(comment_id) if comment_id else current_issue
    eyes_reaction = item_to_react_to.create_reaction("eyes")

    def comment_reply(message: str):
        current_issue.create_comment(message + "\n\n---\n" + bot_suffix)

    comments = current_issue.get_comments()
    replies_text = ""
    if comment_id:
        replies_text = "\nComments:\n" + "\n".join(
            [
                issue_comment_prompt.format(
                    username=comment.user.login,
                    reply=comment.body,
                ) for comment in comments
            ]
        )

    def fetch_file_contents_with_retry():
        retries = 3
        error = None
        for i in range(retries):
            try:
                logger.info(f"Fetching relevant files for the {i}th time...")
                return search_snippets(
                    repo,
                    f"{title}\n{summary}\n{replies_text}",
                    num_files=num_of_snippets_to_query,
                    branch=None,
                    installation_id=installation_id,
                )
            except Exception as e:
                error = e
                continue
        posthog.capture(
            username, "fetching_failed", properties={"error": error, **metadata}
        )
        raise error

    logger.info("Fetching relevant files...")
    try:
        snippets, tree = fetch_file_contents_with_retry()
        assert len(snippets) > 0
    except Exception as e:
        logger.error(e)
        comment_reply(
            "It looks like an issue has occured around fetching the files. Perhaps the repo has not been initialized: try removing this repo and adding it back. I'll try again in a minute. If this error persists contact team@sweep.dev."
        )
        raise e

    num_full_files = 2
    num_extended_snippets = 2

    most_relevant_snippets = snippets[:num_full_files]
    snippets = snippets[:-num_full_files]
    logger.info("Expanding snippets...")
    for snippet in most_relevant_snippets:
        current_snippet = snippet
        _chunks, metadatas, _ids = chunker.call(
            current_snippet.content, 
            current_snippet.file_path
        )
        segmented_snippets = [
            Snippet(
                content=current_snippet.content,
                start=metadata["start"],
                end=metadata["end"],
                file_path=metadata["file_path"],
            ) for metadata in metadatas
        ]
        index = 0
        while index < len(segmented_snippets) and segmented_snippets[index].start <= current_snippet.start:
            index += 1
        index -= 1
        for i in range(index + 1, min(index + num_extended_snippets + 1, len(segmented_snippets))):
            current_snippet += segmented_snippets[i]
        for i in range(index - 1, max(index - num_extended_snippets - 1, 0), -1):
            current_snippet = segmented_snippets[i] + current_snippet
        snippets.append(current_snippet)

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

    snippets = snippets[:min(len(snippets), max_num_of_snippets)]

    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary + replies_text,
        snippets=snippets,
        tree=tree, # TODO: Anything in repo tree that has something going through is expanded
    )
    sweep_bot = SweepBot.from_system_message_content(
        human_message=human_message, repo=repo, is_reply=bool(comments)
    )
    try:
        sweepbot_retries = 3
        for i in range(sweepbot_retries):
            logger.info("CoT retrieval...")
            if sweep_bot.model == "gpt-4-32k-0613":
                sweep_bot.cot_retrieval()
            logger.info("Fetching files to modify/create...")
            file_change_requests = sweep_bot.get_files_to_change()

            # Group file_change_requests by filename
            file_change_requests_grouped = {}
            for file_change_request in file_change_requests:
                if file_change_request.filename not in file_change_requests_grouped:
                    file_change_requests_grouped[file_change_request.filename] = []
                file_change_requests_grouped[file_change_request.filename].append(file_change_request)

            # Process each group of file_change_requests
            for filename, file_change_requests in file_change_requests_grouped.items():
                # Fuse instructions of all file_change_requests for this file
                instructions = "\n".join(file_change_request.instructions for file_change_request in file_change_requests)
                
                # Create a new file_change_request with the fused instructions
                file_change_request = FileChangeRequest(filename=filename, instructions=instructions, change_type=file_change_requests[0].change_type)

                try:
                    contents = repo.get_contents(file_change_request.filename)
                    if contents:
                        file_change_request.change_type = "modify"
                    else:
                        file_change_request.change_type = "create"
                except:
                    file_change_request.change_type = "create"
            logger.info("Getting response from ChatGPT...")
            reply = sweep_bot.chat(reply_prompt, message_key="reply")
            sweep_bot.delete_messages_from_chat("reply")
            logger.info("Sending response...")
            new_line = '\n'
            comment_reply(
                reply
                + "\n\n"
                + collapsible_template.format(
                    summary="Some code snippets I looked at (click to expand). If some file is missing from here, you can mention the path in the ticket description.",
                    body="\n".join(
                        [
                            f"https://github.com/{organization}/{repo_name}/blob/{repo.get_commits()[0].sha}/{snippet.file_path}#L{max(snippet.start, 1)}-L{min(snippet.end, snippet.content.count(new_line))}\n"
                            for snippet in snippets
                        ]
                    ),
                )
            )

            logger.info("Generating PR...")
            pull_request = sweep_bot.generate_pull_request()

            logger.info("Making PR...")
            response = create_pr(file_change_requests, pull_request, sweep_bot, username, installation_id, issue_number)
            if not response or not response["success"]: raise Exception("Failed to create PR")
            pr = response["pull_request"]
            current_issue.create_reaction("rocket")
            try:
                eyes_reaction.delete()
            except:
                pass
            try:
                changes_required, review_comment = review_pr(repo=repo, pr=pr, issue_url=issue_url, username=username, 
                        repo_description=repo_description, title=title, 
                        summary=summary, replies_text=replies_text, tree=tree)
                logger.info(f"Addressing review comment {review_comment}")
                if changes_required:
                    on_comment(repo_full_name=repo_full_name, 
                            repo_description=repo_description, 
                            comment=review_comment,
                            username=username, 
                            installation_id=installation_id,
                            pr_path=None,
                            pr_line_position=None,
                            pr_number=pr.number)
            except Exception as e:
                logger.error(e)
            break
    except openai.error.InvalidRequestError as e:
        logger.error(e)
        comment_reply(
            "I'm sorry, but it looks our model has ran out of context length. We're trying to make this happen less, but one way to mitigate this is to code smaller files. If this error persists contact team@sweep.dev."
        )
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Invalid request error / context length",
                **metadata,
            },
        )
        raise e
    except Exception as e:
        logger.error(e)
        comment_reply(
            "I'm sorry, but it looks like an error has occured. Try removing and re-adding the sweep label. If this error persists contact team@sweep.dev."
        )
        posthog.capture(
            username,
            "failed",
            properties={"error": str(e), "reason": "Generic error", **metadata},
        )
        raise e
    else:
        try:
            eyes_reaction.delete()
        except:
            pass
        item_to_react_to.create_reaction("rocket")

    posthog.capture(username, "success", properties={**metadata})
    logger.info("on_ticket success")
    return {"success": True}

