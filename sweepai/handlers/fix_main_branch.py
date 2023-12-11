from sweepai.events import CheckRunCompleted


def fix_main_branch(request: CheckRunCompleted, repo, g):
    # called if this is the most recent commit in the repo + it's broken
    # if it is, we construct a simple prompt using pr_utils
    pass