import time
import os
from github import Github
from loguru import logger

import os
from github import Github
from loguru import logger

GITHUB_BOT_TOKEN = os.getenv('GITHUB_BOT_TOKEN')

def create_issue(repo_name, title, body):
    if GITHUB_BOT_TOKEN is None:
        logger.error("GITHUB_BOT_TOKEN is not set")
        return
    g = Github(GITHUB_BOT_TOKEN)
    repo = g.get_repo(repo_name)
    issue = repo.create_issue(title=title, body=body)
    logger.info(f"Issue URL: {issue.html_url}")

if __name__ == "__main__":
    # create_issue("sweepai/bot-internal", "Sweep: Modify the logic in tree to only show the sibling files where a snippet was retrieved from", " ")
    # create_issue("sweepai/bot-internal", "Sweep: Add eyes reaction on comment replies", " ")
    create_issue("sweepai/sweep","Sweep: Add eyes reaction to replies in on_comment when they have been addressed using comment id", " ")
