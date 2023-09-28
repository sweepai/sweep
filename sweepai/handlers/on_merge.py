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


def process_commits(request_dict):
    """
    Process the commits from the request dictionary.
    """
    if "commits" in request_dict and len(request_dict["commits"]) > 0:
        head_commit = request_dict["commits"][0]
        all_commits = request_dict["commits"] if "commits" in request_dict else []
        # create a huge commit object with all the commits
        for commit in all_commits:
            logger.info(f"Commit: {commit}")
            head_commit["added"] += commit["added"]
            head_commit["modified"] += commit["modified"]
    else:
        logger.info("No commit found")
        return None
    return head_commit

def check_files(head_commit):
    """
    Check if the commit has any added or modified files.
    """
    if not head_commit["added"] and not head_commit["modified"]:
        logger.info("No files added or modified")
        return None
    changed_files = head_commit["added"] + head_commit["modified"]
    logger.info(f"Changed files: {changed_files}")
    return changed_files

def check_merge_to_master(ref, repo):
    """
    Check if the commit is a merge to master.
    """
    if not ref.startswith("refs/heads/") or ref[
        len("refs/heads/") :
    ] != SweepConfig.get_branch(repo):
        logger.info("Not a merge to master")
        return None
    return True

def check_debounce(repo):
    """
    Check if the repo is in the merge_rule_debounce dictionary and if the difference between the current time and the time stored in the dictionary is less than DEBOUNCE_TIME seconds.
    """
    if (
        repo in merge_rule_debounce
        and time.time() - merge_rule_debounce[repo] < DEBOUNCE_TIME
    ):
        return None
    return True

def get_rules_and_update_debounce(repo):
    """
    Get the rules for the repo and update the merge_rule_debounce dictionary with the current time for the current repo.
    """
    rules = get_rules(repo)
    # update the merge_rule_debounce dictionary with the current time for the current repo
    merge_rule_debounce[repo] = time.time()
    if not rules:
        logger.info("No rules found")
        return None
    return rules

def check_lines_changed(full_commit):
    """
    Check if the total lines changed is less than the CHANGE_THRESHOLD.
    """
    total_lines_changed = full_commit.stats.total
    if total_lines_changed < CHANGE_THRESHOLD:
        return None
    return total_lines_changed

def process_files(changed_files, rules, repo, chat_logger, commit_author):
    """
    Process each changed file and create an issue if necessary.
    """
    total_prs = 0
    total_files_changed = len(changed_files)
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
    return total_prs, total_files_changed

def capture_metrics(commit_author, total_lines_changed, total_prs, total_files_changed):
    """
    Capture some metrics if there are any rules.
    """
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

# @LogTask()
def on_merge(request_dict, chat_logger):
    head_commit = process_commits(request_dict)
    if head_commit is None:
        return
    changed_files = check_files(head_commit)
    if changed_files is None:
        return
    _, g = get_github_client(request_dict["installation"]["id"])
    repo = g.get_repo(request_dict["repository"]["full_name"])
    if not check_merge_to_master(request_dict["ref"], repo):
        return
    if not check_debounce(repo):
        return
    rules = get_rules_and_update_debounce(repo)
    if rules is None:
        return
    full_commit = repo.get_commit(head_commit["id"])
    total_lines_changed = check_lines_changed(full_commit)
    if total_lines_changed is None:
        return
    commit_author = head_commit["author"]["username"]
    total_prs, total_files_changed = process_files(changed_files, rules, repo, chat_logger, commit_author)
    capture_metrics(commit_author, total_lines_changed, total_prs, total_files_changed)
