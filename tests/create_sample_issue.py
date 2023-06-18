import time
import os
from github import Github
from loguru import logger

def create_issue(repo_name, title, body):
    access_token = os.environ.get("ACCESS_TOKEN")
    g = Github(access_token)
    repo = g.get_repo(repo_name)
    issue = repo.create_issue(title=title, body=body)
    logger.info(f"Issue URL: {issue.html_url}")

if __name__ == "__main__":
    # create_issue("sweepai/bot-internal", "Sweep: Modify the logic in tree to only show the sibling files where a snippet was retrieved from", " ")
    # create_issue("sweepai/bot-internal", "Sweep: Add eyes reaction on comment replies", " ")
    create_issue("sweepai/dev-sandbox", "Sweep: Add some more requirements to train a pytorch model, and add a new file which does so", " ")
