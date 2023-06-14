"""
On Github ticket, get ChatGPT to deal with it
"""

import os
import openai

from loguru import logger
from github import Github, UnknownObjectException

from src.core.models import ChatGPT, FileChange, PullRequest
from src.core.prompts import (
    pr_code_prompt,
    pull_request_prompt,
)

from src.utils.github_utils import get_relevant_directories_remote, make_valid_string

github_access_token = os.environ.get("GITHUB_TOKEN")
openai.api_key = os.environ.get("OPENAI_API_KEY")

g = Github(github_access_token)


def on_comment(
    title: str,
    summary: str,
    issue_number: int,
    issue_url: str,
    username: str,
    repo_full_name: str,
    repo_description: str,
    ref: str,
):
    _, repo_name = repo_full_name.split("/")

    repo = g.get_repo(repo_full_name)
    # src_contents = repo.get_contents("src", ref=ref)
    relevant_directories, relevant_files = get_relevant_directories_remote(title)  # type: ignore

    chatGPT = ChatGPT()
    parsed_files: list[FileChange] = []
    while not parsed_files:
        pr_code_response = chatGPT.chat(pr_code_prompt)
        if pr_code_response:
            files = pr_code_response.split("File: ")[1:]
            while files and files[0] == "":
                files = files[1:]
            if not files:
                # TODO(wzeng): Fuse changes back using GPT4
                parsed_files = []
                chatGPT.undo()
                continue
            for file in files:
                try:
                    parsed_file = FileChange.from_string(file)
                    parsed_files.append(parsed_file)
                except Exception:
                    parsed_files = []
                    chatGPT.undo()
                    continue
    logger.info("Accepted ChatGPT result")

    pr_texts: PullRequest | None = None
    while pr_texts is None:
        pr_texts_response = chatGPT.chat(pull_request_prompt)
        try:
            pr_texts = PullRequest.from_string(pr_texts_response)
        except Exception:
            chatGPT.undo()

    branch_name = make_valid_string(
        f"sweep/Issue_{issue_number}_{make_valid_string(title.strip())}"
    ).replace(" ", "_")[:250]
    base_branch = repo.get_branch(repo.default_branch)
    try:
        repo.create_git_ref(f"refs/heads/{branch_name}", base_branch.commit.sha)
    except Exception as e:
        logger.error(f"Error: {e}")

    for file in parsed_files:
        commit_message = f"sweep: {file.description[:50]}"

        try:
            # TODO: check this is single file
            contents = repo.get_contents(file.filename)
            assert not isinstance(contents, list)
            repo.update_file(
                file.filename,
                commit_message,
                file.code,
                contents.sha,
                branch=branch_name,
            )
        except UnknownObjectException:
            repo.create_file(
                file.filename, commit_message, file.code, branch=branch_name
            )

    repo.create_pull(
        title=pr_texts.title,
        body=pr_texts.content,
        head=branch_name,
        base=repo.default_branch,
    )
    return {"success": True}
