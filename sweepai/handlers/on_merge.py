"""
This file contains the on_merge handler which is called when a pull request is merged to master.
on_merge is called by sweepai/api.py
"""
import time

from logn import LogTask, logger
from sweepai.config.client import SweepConfig, get_rules
from sweepai.core.post_merge import PostMerge
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client

# change threshold for number of lines changed
CHANGE_THRESHOLD = 25

# dictionary to map from github repo to the last time a rule was activated
merge_rule_debounce = {}

# debounce time in seconds
DEBOUNCE_TIME = 120


# @LogTask()
def get_head_commit(request_dict):
    if "commits" in request_dict and len(request_dict["commits"]) > 0:
        head_commit = request_dict["commits"][0]
        all_commits = request_dict["commits"] if "commits" in request_dict else []
        for commit in all_commits:
            logger.info(f"Commit: {commit}")
            head_commit["added"] += commit["added"]
            head_commit["modified"] += commit["modified"]
        return head_commit
    else:
        logger.info("No commit found")
        return None

def get_changed_files(head_commit):
    if not head_commit["added"] and not head_commit["modified"]:
        logger.info("No files added or modified")
        return None
    changed_files = head_commit["added"] + head_commit["modified"]
    logger.info(f"Changed files: {changed_files}")
    return changed_files

def get_repo(request_dict):
    _, g = get_github_client(request_dict["installation"]["id"])
    repo = g.get_repo(request_dict["repository"]["full_name"])
    return repo

def check_merge_to_master(ref, repo):
    if not ref.startswith("refs/heads/") or ref[
        len("refs/heads/") :
    ] != SweepConfig.get_branch(repo):
        logger.info("Not a merge to master")
        return False
    return True

def check_debounce(repo):
    if (
        repo in merge_rule_debounce
        and time.time() - merge_rule_debounce[repo] < DEBOUNCE_TIME
    ):
        return True
    return False

def update_debounce(repo):
    merge_rule_debounce[repo] = time.time()

def get_rules(repo):
    rules = get_rules(repo)
    if not rules:
        logger.info("No rules found")
        return None
    return rules

def get_full_commit(head_commit, repo):
    full_commit = repo.get_commit(head_commit["id"])
    return full_commit

def check_change_threshold(full_commit):
    total_lines_changed = full_commit.stats.total
    if total_lines_changed < CHANGE_THRESHOLD:
        return False
    return True

def get_commit_author(head_commit):
    commit_author = head_commit["author"]["username"]
    return commit_author

def create_issues(changed_files, rules, repo, commit_author, chat_logger):
    total_prs = 0
    for file in changed_files:
        if total_prs >= 2:
            logger.info("Too many PRs")
            break
        file_contents = repo.get_contents(file).decoded_content.decode("utf-8")
        issue_title, issue_description = PostMerge(
            chat_logger=chat_logger
        ).check_for_issues(rules=rules, file_path=file, file_contents=file_contents)
        logger.info(f"Title: {issue_title}")
        logger.info(f"Description: {issue_description}")
        if issue_title:
            logger.info(f"Changes required in {file}")
            repo.create_issue(
                title="Sweep: " + issue_title,
                body=issue_description,
                assignees=[commit_author],
            )
            total_prs += 1
    return total_prs

def capture_posthog(commit_author, total_lines_changed, total_prs, total_files_changed):
    if rules:
        posthog.capture(
            commit_author,
            "rule_pr_created",
            {
                "total_lines_changed": total_lines_changed,
                "total_prs": total_prs,
                "total_files_changed": total_files_changed,
            },
        )

def on_merge(request_dict, chat_logger):
    head_commit = get_head_commit(request_dict)
    if head_commit is None:
        return None
    changed_files = get_changed_files(head_commit)
    if changed_files is None:
        return None
    repo = get_repo(request_dict)
    ref = request_dict["ref"]
    if not check_merge_to_master(ref, repo):
        return None
    if check_debounce(repo):
        return
    update_debounce(repo)
    rules = get_rules(repo)
    if rules is None:
        return None
    full_commit = get_full_commit(head_commit, repo)
    if not check_change_threshold(full_commit):
        return None
    commit_author = get_commit_author(head_commit)
    total_prs = create_issues(changed_files, rules, repo, commit_author, chat_logger)
    total_files_changed = len(changed_files)
    capture_posthog(commit_author, full_commit.stats.total, total_prs, total_files_changed)
