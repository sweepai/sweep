"""
This file contains the on_merge handler which is called when a pull request is merged to master.
on_merge is called by sweepai/api.py
"""
import copy
import time

from sweepai.logn import logger
from sweepai.config.client import SweepConfig, get_rules, get_blocked_dirs
from sweepai.core.post_merge import PostMerge
from sweepai.handlers.pr_utils import make_pr
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client

# change threshold for number of lines changed
CHANGE_BOUNDS = (25, 1500)

# dictionary to map from github repo to the last time a rule was activated
merge_rule_debounce = {}

# debounce time in seconds
DEBOUNCE_TIME = 120

diff_section_prompt = """
<file_diff file="{diff_file_path}">
{diffs}
</file_diff>"""

def comparison_to_diff(comparison, blocked_dirs):
    pr_diffs = []
    for file in comparison.files:
        diff = file.patch
        if (
            file.status == "added"
            or file.status == "modified"
            or file.status == "removed"
        ):
            if any(file.filename.startswith(dir) for dir in blocked_dirs):
                continue
            pr_diffs.append((file.filename, diff))
        else:
            logger.info(
                f"File status {file.status} not recognized"
            )  # TODO(sweep): We don't handle renamed files
    formatted_diffs = []
    for file_name, file_patch in pr_diffs:
        format_diff = diff_section_prompt.format(
            diff_file_path=file_name, diffs=file_patch
        )
        formatted_diffs.append(format_diff)
    return "\n".join(formatted_diffs)

def on_merge(request_dict: dict, chat_logger: ChatLogger):
    before_sha = request_dict['before']
    after_sha = request_dict['after']
    commit_author = request_dict['sender']['login']
    ref = request_dict["ref"]
    if not ref.startswith("refs/heads/"): return
    user_token, g = get_github_client(request_dict["installation"]["id"])
    repo = g.get_repo(request_dict["repository"]["full_name"]) # do this after checking ref
    if ref[len("refs/heads/"):] != SweepConfig.get_branch(repo):
        return
    blocked_dirs = get_blocked_dirs(repo)
    comparison = repo.compare(before_sha, after_sha)
    commits_diff = comparison_to_diff(comparison, blocked_dirs)
    # check if the current repo is in the merge_rule_debounce dictionary
    # and if the difference between the current time and the time stored in the dictionary is less than DEBOUNCE_TIME seconds
    if (
        repo.full_name in merge_rule_debounce
        and time.time() - merge_rule_debounce[repo.full_name] < DEBOUNCE_TIME
    ):
        return
    merge_rule_debounce[repo.full_name] = time.time()
    if not (commits_diff.count("\n") > CHANGE_BOUNDS[0] and commits_diff.count("\n") < CHANGE_BOUNDS[1]):
        return
    
    rules = get_rules(repo)
    if not rules:
        return
    for rule in rules:
        chat_logger.data["title"] = f"Sweep Rules - {rule}"
        changes_required, issue_title, issue_description = PostMerge(
            chat_logger=chat_logger
        ).check_for_issues(rule=rule, diff=commits_diff)
        if changes_required:
            make_pr(
                title="[Sweep Rules] " + issue_title,
                repo_description=repo.description,
                summary=issue_description,
                repo_full_name=request_dict["repository"]["full_name"],
                installation_id=request_dict["installation"]["id"],
                user_token=user_token,
                use_faster_model=chat_logger.use_faster_model(g),
                username=commit_author,
                chat_logger=chat_logger,
                rule=rule,
            )
            posthog.capture(
                commit_author,
                "rule_pr_created"
            )