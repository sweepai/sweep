'''
On Github ticket, get ChatGPT to deal with it
'''

# TODO: Add file validation

import os
import openai

from loguru import logger
import modal
from tabulate import tabulate

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
from sweepai.utils.chat_logger import ChatLogger, discord_log_error

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

update_index = modal.Function.lookup(DB_NAME, "update_index")

sep = "\n---\n"
bot_suffix_starring = "⭐ If you are enjoying Sweep, please star our repo at https://github.com/sweepai/sweep so more people can hear about us!"
bot_suffix = f"\n{sep}I'm a bot that handles simple bugs and feature requests but I might make mistakes. Please be kind!"

stars_suffix = "⭐ In the meantime, consider starring our repo at https://github.com/sweepai/sweep so more people can hear about us!"

collapsible_template = '''
<details>
  <summary>{summary}</summary>

  {body}
</details>
'''

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

    # Add emojis
    eyes_reaction = item_to_react_to.create_reaction("eyes")

    # Creates progress bar ASCII for 0-5 states
    progress_headers = [
        None,
        "Step 1: 🔍 Code Search",
        "Step 2: 🧐 Snippet Analysis",
        "Step 3: 📝 Planning",
        "Step 4: ⌨️ Coding",
        "Step 5: 🔁 Code Review"
    ]
    def get_progress_bar(index, errored=False):
        if index < 0: index = 0
        index *= 20
        index = min(100, index)
        if errored:
            return f"![{index}%](https://progress-bar.dev/{index}/?&title=Progress&width=600) 🚫"
        return f"![{index}%](https://progress-bar.dev/{index}/?&title=Progress&width=600)" + ("\n" + stars_suffix if index != -1 else "")

    issue_comment = current_issue.create_comment(f"{get_progress_bar(0)}\n{sep}I am currently looking into this ticket! I will update the progress of the ticket in this comment. I am currently searching through your code, looking for relevant snippets.{bot_suffix}")
    past_messages = {}
    def comment_reply(message: str, index: int):
        # Only update the progress bar if the issue generation errors.
        errored = (index == -1)
        current_index = index
        if index >= 0:
            past_messages[index] = message

        # Include progress history
        agg_message = None
        for i in range(current_index + 1):
            if i in past_messages:
                header = progress_headers[i]
                if header is not None: header = "## " + header + "\n"
                else: header = "No header\n"
                msg = header + past_messages[i]
                if agg_message is None:
                    agg_message = msg
                else:
                    agg_message = agg_message + f"\n{sep}" + msg

        # Update the issue comment
        issue_comment.edit(f"{get_progress_bar(current_index, errored)}\n{sep}{agg_message}{bot_suffix}")

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

    def log_error(error_type, message):
        content = f"**{error_type} Error**\n{issue_url} from {username}\n{message}"
        discord_log_error(content)

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
            "It looks like an issue has occured around fetching the files. Perhaps the repo has not been initialized: try removing this repo and adding it back. I'll try again in a minute. If this error persists contact team@sweep.dev.",
            -1
        )
        log_error("File Fetch", str(e))
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

    chat_logger = ChatLogger({
        'repo_name': repo_name,
        'issue_url': issue_url,
        'username': username,
        'title': title,
        'summary': summary + replies_text,
    })
    sweep_bot = SweepBot.from_system_message_content(
        human_message=human_message, repo=repo, is_reply=bool(comments), chat_logger=chat_logger
    )
    sweepbot_retries = 3
    try:
        for i in range(sweepbot_retries):
            # ANALYZE SNIPPETS
            logger.info("CoT retrieval...")
            if sweep_bot.model == "gpt-4-32k-0613":
                sweep_bot.cot_retrieval()

            newline = '\n'
            comment_reply(
                "I found the following snippets in your repository. I will now analyze this snippets and come up with a plan."
                + "\n\n"
                + collapsible_template.format(
                    summary="Some code snippets I looked at (click to expand). If some file is missing from here, you can mention the path in the ticket description.",
                    body="\n".join(
                        [
                            f"https://github.com/{organization}/{repo_name}/blob/{repo.get_commits()[0].sha}/{snippet.file_path}#L{max(snippet.start, 1)}-L{min(snippet.end, snippet.content.count(newline))}\n"
                            for snippet in snippets
                        ]
                    ),
                ),
                1
            )

            # COMMENT ON ISSUE
            # TODO: removed issue commenting here
            logger.info("Fetching files to modify/create...")
            file_change_requests = sweep_bot.get_files_to_change()
            file_change_requests = sweep_bot.validate_file_change_requests(file_change_requests)
            table = tabulate(
                [[f"`{file_change_request.filename}`", file_change_request.instructions] for file_change_request in file_change_requests],
                headers=["File Path", "Proposed Changes"],
                tablefmt="pipe"
            )
            print(table)
            comment_reply(
                "From looking through the relevant snippets, I decided to make the following modifications:\n\n" + table + "\n\n",
                2
            )

            # CREATE PR METADATA
            logger.info("Generating PR...")
            pull_request = sweep_bot.generate_pull_request()
            pull_request_content = pull_request.content.strip().replace("\n", "\n>")
            pull_request_summary = f"**{pull_request.title}**\n`{pull_request.branch_name}`\n>{pull_request_content}\n"

            comment_reply(
                f"I have created a plan for writing the pull request. I am now working on executing my plan and coding the required changes to address this issue. Here is the planned pull request:\n\n{pull_request_summary}",
                3
            )

            # WRITE PULL REQUEST
            logger.info("Making PR...")
            response = create_pr(file_change_requests, pull_request, sweep_bot, username, installation_id, issue_number)
            if not response or not response["success"]: raise Exception("Failed to create PR")
            pr = response["pull_request"]
            current_issue.create_reaction("rocket")
            comment_reply(
                "I have finished coding the issue. I am now reviewing it for completeness.",
                4
            )

            try:
                current_issue.delete_reaction(eyes_reaction.id)
            except:
                pass
            try:
                # CODE REVIEW
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

            # Completed code review
            comment_reply(
                "Success! 🚀",
                5
            )
            break
    except openai.error.InvalidRequestError as e:
        logger.error(e)
        comment_reply(
            "I'm sorry, but it looks our model has ran out of context length. We're trying to make this happen less, but one way to mitigate this is to code smaller files. If this error persists contact team@sweep.dev.",
            -1
        )
        log_error("Context Length", str(e))
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
            "I'm sorry, but it looks like an error has occured. Try removing and re-adding the sweep label. If this error persists contact team@sweep.dev.",
            -1
        )
        log_error("Workflow", str(e))
        posthog.capture(
            username,
            "failed",
            properties={"error": str(e), "reason": "Generic error", **metadata},
        )
        raise e
    else:
        try:
            item_to_react_to.delete_reaction(eyes_reaction.id)
        except:
            pass
        item_to_react_to.create_reaction("rocket")

    posthog.capture(username, "success", properties={**metadata})
    logger.info("on_ticket success")
    return {"success": True}

