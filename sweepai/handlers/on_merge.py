from sweepai.config.client import get_rules, SweepConfig
from sweepai.utils.github_utils import get_github_client
from sweepai.core.post_merge import PostMerge
from loguru import logger

# change threshold for number of lines changed
CHANGE_THRESHOLD = 50

def on_merge(request_dict):
    head_commit = request_dict["head_commit"]
    ref = request_dict["ref"]
    if not head_commit:
        logger.info("No head commit found")
        return None
    commit_message = head_commit["message"]
    if not head_commit["added"] and \
        not head_commit["modified"]:
        logger.info("No files added or modified")
        return None
    changed_files = head_commit["added"] + \
        head_commit["modified"]
    logger.info(f"Changed files: {changed_files}")
    _, g = get_github_client(request_dict["installation"]["id"])
    repo = g.get_repo(request_dict["repository"]["full_name"])
    if not ref.startswith("refs/heads/") or ref[len("refs/heads/"):] != SweepConfig.get_branch(repo):
        logger.info("Not a merge to master")
        return None
    rules = get_rules(repo)
    full_commit = repo.get_commit(head_commit['id'])
    total_lines_changed = full_commit.stats.total
    if total_lines_changed < CHANGE_THRESHOLD:
        return None
    commit_author = head_commit["author"]["username"]
    for file in changed_files:
        file_contents = repo.get_contents(file).decoded_content.decode("utf-8")
        issue_title, issue_description = PostMerge().check_for_issues(rules=rules, file_path=file, file_contents=file_contents)
        logger.info(f"Title: {issue_title}")
        logger.info(f"Description: {issue_description}")
        if issue_title:
            logger.info(f"Changes required in {file}")
            repo.create_issue(title="Sweep: " + issue_title, body=issue_description, assignees=[commit_author])