from github import Repository
from loguru import logger
from requests.exceptions import Timeout
import requests

def hydrate_sandbox_cache(repo_full_name: str, user_token: str, sandbox_url: str):
    logger.info("Hydrating cache of sandbox.")
    try:
        requests.post(
            sandbox_url,
            json={
                "repo_url": f"https://github.com/{repo_full_name}",
                "token": user_token,
            },
            timeout=2,
        )
    except Timeout:
        logger.info("Sandbox hydration timed out.")
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.warning(
            f"Error hydrating cache of sandbox: {e}"
        )
    logger.info("Done sending, letting it run in the background.")

def check_sweep_yaml_exists(repo: Repository):
    sweep_yml_exists = False
    for content_file in repo.get_contents(""):
        if content_file.name == "sweep.yaml":
            sweep_yml_exists = True
            break
    return sweep_yml_exists

def create_pull_request(repo: Repository, pr_changes, pr_actions_message, revert_buttons_list, rules_buttons_list, GITHUB_LABEL_NAME):
    pr = repo.create_pull(
        title=pr_changes.title,
        body=pr_actions_message + pr_changes.body,
        head=pr_changes.pr_head,
        base=SweepConfig.get_branch(repo),
    )

    pr.create_issue_comment(sandbox_execution_comment_contents)

    if revert_buttons:
        pr.create_issue_comment(revert_buttons_list.serialize())
    if rule_buttons:
        pr.create_issue_comment(rules_buttons_list.serialize())

    pr.add_to_labels(GITHUB_LABEL_NAME)
    return pr
