"""
On Github ticket, get ChatGPT to deal with it
"""

# TODO: Add file validation

import os
import openai

from loguru import logger
import modal

from src.core.entities import Snippet
from src.core.prompts import (
    reply_prompt,
)
from src.core.sweep_bot import SweepBot
from src.core.prompts import issue_comment_prompt
from src.handlers.on_review import review_pr
from src.utils.event_logger import posthog
from src.utils.github_utils import get_github_client, search_snippets
from src.utils.prompt_constructor import HumanMessagePrompt
from src.utils.constants import DB_NAME, PREFIX

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

chunker = modal.Function.lookup("utils", "Chunking.chunk")

num_of_snippets_to_query = 10
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

    # update_index.call(
    #     repo_full_name,
    #     installation_id=installation_id,
    # )
    if current_issue.state == 'closed':
if current_issue.state == 'closed':
    logger.info(f'Issue is closed, not retrying. User: {username}')
    posthog.capture("closed_issue", properties={})
    except Exception as e:
        logger.error(e)
        comment_reply(
            "It looks like an issue has occured around fetching the files. Perhaps the repo has not been initialized: try removing this repo and adding it back. I'll try again in a minute. If this error persists contact team@sweep.dev."
        )
        raise e

    # reversing to put most relevant at the bottom
    snippets: list[Snippet] = snippets[::-1]

    num_full_files = 2
    num_extended_snippets = 2

    most_relevant_snippets = snippets[-num_full_files:]
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
        logger.info("CoT retrieval...")
        if sweep_bot.model == "gpt-4-32k-0613":
            sweep_bot.cot_retrieval()
        logger.info("Fetching files to modify/create...")
        file_change_requests = sweep_bot.get_files_to_change()
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
                        for snippet in snippets[::-1]
                    ]
                ),
            )
        )

        logger.info("Generating PR...")
        pull_request = sweep_bot.generate_pull_request()

        logger.info("Making PR...")
        pull_request.branch_name = sweep_bot.create_branch(pull_request.branch_name)
        sweep_bot.change_files_in_github(file_change_requests, pull_request.branch_name)

        # Include issue number in PR description
        pr_description = f"{pull_request.content}\n\nFixes #{issue_number}."

        pr = repo.create_pull(
            title=pull_request.title,
            body=pr_description,
            head=pull_request.branch_name,
            base=repo.default_branch,
        )
        current_issue.create_reaction("rocket")
        try:
            review_pr(repo=repo, pr=pr, issue_url=issue_url, username=username, 
                    repo_description=repo_description, title=title, 
                    summary=summary, replies_text=replies_text, installation_id=installation_id, snippets=snippets, tree=tree)
        except Exception as e:
            logger.error(e)
    except openai.error.InvalidRequestError as e:
        logger.error(e)
        comment_reply(
            "I'm sorry, but it looks our model has ran out of context length. We're trying to make this happen less, but one way to mitigate this is to code smaller files. I'll try again in a minute. If this error persists contact team@sweep.dev."
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
            "I'm sorry, but it looks like an error has occured. Try removing and re-adding the sweep label. I'll try again in a minute. If this error persists contact team@sweep.dev."
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