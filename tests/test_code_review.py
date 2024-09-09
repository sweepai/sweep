# as an mvp this will take a pr and then review the code to generate a summary, then a comprehensive list of valid concerns
# todo: citations, more complex code analysis
import os
from dotenv import load_dotenv
from github import Github
from loguru import logger

from sweepai.core.review_utils import PRReviewBot, get_pr_changes
from sweepai.utils.chat_logger import ChatLogger

load_dotenv(dotenv_path=".env", override=True, verbose=True)

# Create a GitHub instance using your access token or username and password
url = "https://github.com/poulh/legacyCodeConverter/pull/2"

# Specify the repository and pull request number
repo_name = url.split("https://github.com/")[-1].split("/pull")[0]
pr_number = int(url.split("/pull/")[1].split("/")[0])

GITHUB_PAT = os.environ.get("GITHUB_PAT", None)

# Get the repository and pull request objects
def temp_pr_changes(url):
    g = Github(GITHUB_PAT)
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    # Fetch the diff
    pr_changes, _, _ = get_pr_changes(repo, pr)
    return pr_changes

pr_changes = temp_pr_changes(url)
breakpoint()
# breakpoint()
# exit()
chat_logger=ChatLogger({"username": "Code Review","title": "Code Review Test",})
review_bot = PRReviewBot()
breakpoint()
