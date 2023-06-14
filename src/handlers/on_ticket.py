"""
On Github ticket, get ChatGPT to deal with it
"""

# TODO: Add file validation

import os
import openai

from loguru import logger
from github import Github

from src.core.prompts import (
    system_message_prompt,
    human_message_prompt,
    reply_prompt,
)
from src.core.sweep_bot import SweepBot
# from src.utils.github_utils import get_relevant_directories_remote, get_github_client
from src.utils.github_utils import get_relevant_directories, get_github_client

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

g = Github(github_access_token)

bot_suffix = "I'm a bot that handles simple bugs and feature requests\
but I might make mistakes. Please be kind!"


def on_ticket(
    title: str,
    summary: str,
    issue_number: int,
    issue_url: str,
    username: str,
    repo_full_name: str,
    repo_description: str,
    installation_id: int,
    relevant_files: str = "",
):
    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR

    logger.info(
        "Calling on_ticket() with the following arguments: {title}, {summary}, {issue_number}, {issue_url}, {username}, {repo_full_name}, {repo_description}, {relevant_files}",
        title=title,
        summary=summary,
        issue_number=issue_number,
        issue_url=issue_url,
        username=username,
        repo_full_name=repo_full_name,
        repo_description=repo_description,
        relevant_files=relevant_files,
    )
    g = get_github_client(installation_id)
    _org_name, repo_name = repo_full_name.split("/")

    logger.info("Getting repo {repo_full_name}", repo_full_name=repo_full_name)
    repo = g.get_repo(repo_full_name)
    # src_contents = repo.get_contents("/")
    # relevant_directories, relevant_files = get_relevant_directories_remote(title, num_files=1)  # type: ignore
    relevant_directories, relevant_files = get_relevant_directories(title, num_files=1)  # type: ignore

    logger.info("Getting response from ChatGPT...")
    human_message = human_message_prompt.format(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        description=summary,
        relevant_directories=relevant_directories,
        relevant_files=relevant_files,
    )
    sweep_bot = SweepBot.from_system_message_content(
        system_message_prompt + "\n\n" + human_message, model="gpt-3.5-turbo", repo=repo
    )
    reply = sweep_bot.chat(reply_prompt)
    sweep_bot.undo()  # not doing it sometimes causes problems: the bot thinks it has already has done the fixes

    logger.info("Sending response...")
    repo.get_issue(number=issue_number).create_comment(reply + "\n\n---\n" + bot_suffix)

    logger.info("Fetching files to modify/create...")
    file_change_requests = sweep_bot.get_files_to_change()

    logger.info("Generating PR...")
    pull_request = sweep_bot.generate_pull_request()

    logger.info("Making PR...")

    pull_request.branch_name = sweep_bot.create_branch(pull_request.branch_name)
    sweep_bot.change_files_in_github(file_change_requests, pull_request.branch_name)

    repo.create_pull(
        title=pull_request.title,
        body=pull_request.content,  # link back to issue
        head=pull_request.branch_name,
        base=repo.default_branch,
    )

    logger.info("Done!")
    return {"success": True}
