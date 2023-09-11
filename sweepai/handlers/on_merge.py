from sweepai.config.client import get_rules, SweepConfig
from sweepai.utils.github_utils import get_github_client
from sweepai.core.post_merge import PostMerge
from loguru import logger
from sweepai.utils.event_logger import posthog

====
CHANGE_THRESHOLD = 50

def on_merge(request_dict, chat_logger):
    if "commits" in request_dict and len(request_dict["commits"]) > 0:
        head_commit = request_dict["commits"][0]
        all_commits = request_dict["commits"] if "commits" in request_dict else []
        # create a huge commit object with all the commits
        for commit in all_commits:
            logger.error(f"Commit: {commit}", exc_info=True)
            head_commit["added"] += commit["added"]
            head_commit["modified"] += commit["modified"]
    else:
        logger.error("No commit found", exc_info=True)
        return None
    ref = request_dict["ref"]
    if not head_commit["added"] and \
        not head_commit["modified"]:
        logger.info("No files added or modified")
        return None
    changed_files = head_commit["added"] + \
        head_commit["modified"]
    ====
    _, g = get_github_client(request_dict["installation"]["id"])
    repo = g.get_repo(request_dict["repository"]["full_name"])
    if not ref.startswith("refs/heads/") or ref[len("refs/heads/"):] != SweepConfig.get_branch(repo):
        ====
        return None
    rules = get_rules(repo)
    if not rules:
        logger.info("No rules found")
        return None
    full_commit = repo.get_commit(head_commit['id'])
    total_lines_changed = full_commit.stats.total
    if total_lines_changed < CHANGE_THRESHOLD:
        return None
    commit_author = head_commit["author"]["username"]
    total_prs = 0
    total_files_changed = len(changed_files)
    for file in changed_files:
        if total_prs >= 2:
            ====
            break
        file_contents = repo.get_contents(file).decoded_content.decode("utf-8")
        issue_title, issue_description = PostMerge(chat_logger=chat_logger).check_for_issues(rules=rules, file_path=file, file_contents=file_contents)
        ====
        if issue_title:
            ====
            repo.create_issue(title="Sweep: " + issue_title, body=issue_description, assignees=[commit_author])
            total_prs += 1
    if rules is not None:
        posthog.capture(commit_author, 'on_merge', {'total_lines_changed': total_lines_changed, 'total_prs': total_prs, 'total_files_changed': total_files_changed})