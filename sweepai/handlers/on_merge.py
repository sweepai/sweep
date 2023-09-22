from sweepai.config.client import get_rules, SweepConfig
from sweepai.utils.github_utils import get_github_client
from sweepai.core.post_merge import PostMerge
from logn import logger, LogTask
from sweepai.utils.event_logger import posthog
from sweepai.utils.safe_priority_queue import SafePriorityQueue
from sweepai.utils.redis_client import redis_client

# change threshold for number of lines changed
CHANGE_THRESHOLD = 25

# global dictionary to track the last time a rule was activated for each repo
last_rule_call_times = SafePriorityQueue()


@LogTask()
def on_merge(request_dict, chat_logger):
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
    ref = request_dict["ref"]
    if not head_commit["added"] and not head_commit["modified"]:
        logger.info("No files added or modified")
        return None
    changed_files = head_commit["added"] + head_commit["modified"]
    logger.info(f"Changed files: {changed_files}")
    _, g = get_github_client(request_dict["installation"]["id"])
    repo = g.get_repo(request_dict["repository"]["full_name"])
    if not ref.startswith("refs/heads/") or ref[
        len("refs/heads/") :
    ] != SweepConfig.get_branch(repo):
        logger.info("Not a merge to master")
        return None
    last_rule_call_time = redis_client.get(f"{repo.full_name}_last_rule_call_time")
    current_time = time.time()
    if last_rule_call_time is not None and current_time - float(last_rule_call_time) < 30:
        last_rule_call_times.put((current_time + 30, repo))
    else:
        rules = get_rules(repo)
        if not rules:
            logger.info("No rules found")
            return None
        redis_client.set(f"{repo.full_name}_last_rule_call_time", current_time)
    full_commit = repo.get_commit(head_commit["id"])
    total_lines_changed = full_commit.stats.total
    if total_lines_changed < CHANGE_THRESHOLD:
        return None
    commit_author = head_commit["author"]["username"]
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
        # Check the SafePriorityQueue for any rules calls that are due and call them
        while not last_rule_call_times.empty() and last_rule_call_times.queue[0][0] <= time.time():
            _, due_repo = last_rule_call_times.get()
            due_rules = get_rules(due_repo)
            if due_rules:
                redis_client.set(f"{due_repo.full_name}_last_rule_call_time", time.time())
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
    # Update the time of the last rules call in the redis_client after each rules call
    redis_client.set(f"{repo.full_name}_last_rule_call_time", time.time())
