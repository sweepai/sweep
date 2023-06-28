import os
from github import Github
from git import Repo
from loguru import logger
from apscheduler.schedulers.blocking import BlockingScheduler

from ..utils.github_utils import get_github_client
from datetime import datetime, timedelta

DAYS_INACTIVE = int(os.getenv('DAYS_INACTIVE', 7))

scheduler = BlockingScheduler()

@scheduler.scheduled_job('interval', days=DAYS_INACTIVE)
def cleanup_inactive_branches(installation_id, repo_name, days_inactive=DAYS_INACTIVE):

    logger.info('Cleaning up inactived branch ...')
    repo = get_github_client(installation_id).get_repo(repo_name)
    RIGHTNOW = datetime.now()

    for branch in repo.get_branches():
        commit = branch.commit

        # Get the date of the last commit
        commit_date = commit.commit.author.date

        days_since_last_commit = (RIGHTNOW - commit_date).days

        if days_since_last_commit > DAYS_INACTIVE:
            logger.info(f'Deleting branch {branch.name}...')
            repo.get_git_ref(f'heads/{branch.name}').delete()

    logger.info('Branch cleanup complete.')

@scheduler.scheduled_job('interval', days=DAYS_INACTIVE)
def cleanup_old_prs(installation_id, repo_name, days_inactive=DAYS_INACTIVE):

    logger.info('Cleaning up old Pull requests ...')
    repo = get_github_client(installation_id).get_repo(repo_name)
    RIGHTNOW = datetime.now()

    for pr in repo.get_pulls(state='open'):
        # Get the date of the last update
        pr_update_date = pr.updated_at

        days_since_last_update = (RIGHTNOW - pr_update_date).days

        if days_since_last_update > DAYS_INACTIVE:
            logger.info(f'Closing pull request #{pr.number}...')
            pr.edit(state='closed')

    logger.info('Pull request cleanup complete.')

if __name__ == "__main__":
    scheduler.start()
