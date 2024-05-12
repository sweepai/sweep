# as an mvp this will take a pr and then review the code to generate a summary, then a comprehensive list of valid concerns

import os
from dotenv import load_dotenv
from github import Github
from loguru import logger

from sweepai.handlers.on_review import PRReviewBot, get_pr_changes

load_dotenv(dotenv_path=".env", override=True, verbose=True)

# Create a GitHub instance using your access token or username and password
GITHUB_PAT = os.environ.get("GITHUB_PAT", None)
g = Github(GITHUB_PAT)

# Specify the repository and pull request number
repo_name = "poulh/legacyCodeConverter"
pr_number = 2

# Get the repository and pull request objects
repo = g.get_repo(repo_name)
pr = repo.get_pull(pr_number)
# Fetch the diff
pr_changes = get_pr_changes(repo, pr)

code_review = PRReviewBot().review_code_changes(pr_changes)
logger.info("Code review summary:" + code_review.diff_summary)
logger.info("Code review issues:" + code_review.issues)
