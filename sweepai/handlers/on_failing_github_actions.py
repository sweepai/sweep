import copy
import posthog

from github import Repository, WorkflowRun
from loguru import logger

from sweepai.config.client import get_gha_enabled
from sweepai.config.server import DEPLOYMENT_GHA_ENABLED
from sweepai.core.context_pruning import RepoContextManager
from sweepai.core.entities import PullRequest
from sweepai.core.sweep_bot import GHA_PROMPT, get_files_to_change_for_gha, validate_file_change_requests
from sweepai.handlers.create_pr import handle_file_change_requests
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo, commit_multi_file_changes, validate_and_sanitize_multi_file_changes
from sweepai.utils.prompt_constructor import get_issue_request
from sweepai.utils.ticket_rendering_utils import get_branch_diff_text, get_failing_gha_logs
from sweepai.utils.ticket_utils import prep_snippets


def on_failing_github_actions(
    problem_statement: str,
    repo: Repository,
    username: str,
    pull_request: PullRequest,
    user_token: str,
    installation_id: int,
    chat_logger: ChatLogger,
):
    # poll for github to check when gha are done
    repo_full_name = repo.full_name
    total_poll_attempts = 0
    total_edit_attempts = 0
    SLEEP_DURATION_SECONDS = 15
    GITHUB_ACTIONS_ENABLED = get_gha_enabled(repo=repo) and DEPLOYMENT_GHA_ENABLED
    GHA_MAX_EDIT_ATTEMPTS = 5 # max number of times to edit PR
    current_commit = pr.head.sha

    main_runs: list[WorkflowRun.WorkflowRun] = list(repo.get_workflow_runs(branch=repo.default_branch, head_sha=pr.base.sha))
    # main_passing = all([run.conclusion in ["success", None] for run in main_runs]) and any([run.conclusion == "success" for run in main_runs])
    main_passing = True

    while GITHUB_ACTIONS_ENABLED and main_passing:
        logger.info(
            f"Polling to see if Github Actions have finished... {total_poll_attempts}"
        )
        # we wait at most 60 minutes
        if total_poll_attempts * SLEEP_DURATION_SECONDS // 60 >= 60:
            logger.debug("Polling for Github Actions has taken too long, giving up.")
            break
        else:
            # wait one minute between check attempts
            total_poll_attempts += 1
            from time import sleep

            sleep(SLEEP_DURATION_SECONDS)
        # refresh the pr
        pr = repo.get_pull(pr.number)
        current_commit = repo.get_pull(pr.number).head.sha # IMPORTANT: resync PR otherwise you'll fetch old GHA runs
        runs = list(repo.get_commit(current_commit).get_check_runs())
        suite_runs = list(repo.get_workflow_runs(branch=pr.head.ref, head_sha=pr.head.sha))
        # if all runs have succeeded or have no result, break
        if all([run.conclusion in ["success", None] and run.status not in ["in_progress", "waiting", "pending", "requested", "queued"] for run in runs]):
            break
        logger.debug(f"Run statuses: {[run.status for run in runs]}")
        # if any of them have failed we retry
        if any([run.conclusion == "failure" for run in runs]):
            failed_runs = [run for run in suite_runs if run.conclusion == "failure"]

            failed_gha_logs: list[str] = get_failing_gha_logs(
                failed_runs,
                installation_id,
            )
            if failed_gha_logs:
                # make edits to the PR
                # TODO: look into rollbacks so we don't continue adding onto errors
                cloned_repo = ClonedRepo( # reinitialize cloned_repo to avoid conflicts
                    repo_full_name,
                    installation_id=installation_id,
                    token=user_token,
                    repo=repo,
                    branch=pr.head.ref,
                )
                diffs = get_branch_diff_text(repo=repo, branch=pr.head.ref, base_branch=pr.base.ref)
                # problem_statement = f"{title}\n{internal_message_summary}\n{replies_text}"
                all_information_prompt = GHA_PROMPT.format(
                    problem_statement=problem_statement,
                    github_actions_logs=failed_gha_logs,
                    changes_made=diffs,
                )
                repo_context_manager: RepoContextManager = prep_snippets(cloned_repo=cloned_repo, query=problem_statement.strip("\n"), ticket_progress=None) # need to do this, can use the old query for speed
                issue_request = get_issue_request(
                    "Fix the following errors to complete the user request.",
                    all_information_prompt,
                )
                file_change_requests, plan = get_files_to_change_for_gha(
                    relevant_snippets=repo_context_manager.current_top_snippets,
                    read_only_snippets=repo_context_manager.read_only_snippets,
                    problem_statement=all_information_prompt,
                    updated_files=modify_files_dict,
                    cloned_repo=cloned_repo,
                    chat_logger=chat_logger,
                )
                validate_file_change_requests(file_change_requests, cloned_repo)
                previous_modify_files_dict: dict[str, dict[str, str | list[str]]] | None = None
                modify_files_dict, _, file_change_requests = handle_file_change_requests(
                    file_change_requests=file_change_requests,
                    request=issue_request,
                    cloned_repo=cloned_repo,
                    username=username,
                    installation_id=installation_id,
                    previous_modify_files_dict=previous_modify_files_dict,
                )
                commit_message = f"feat: Updated {len(modify_files_dict or [])} files"[:50]
                try:
                    new_file_contents_to_commit = {file_path: file_data["contents"] for file_path, file_data in modify_files_dict.items()}
                    previous_file_contents_to_commit = copy.deepcopy(new_file_contents_to_commit)
                    new_file_contents_to_commit, files_removed = validate_and_sanitize_multi_file_changes(
                        cloned_repo.repo,
                        new_file_contents_to_commit,
                        file_change_requests
                    )
                    if files_removed and username:
                        posthog.capture(
                            username,
                            "polluted_commits_error",
                            properties={
                                "old_keys": ",".join(previous_file_contents_to_commit.keys()),
                                "new_keys": ",".join(new_file_contents_to_commit.keys()) 
                            },
                        )
                    commit = commit_multi_file_changes(cloned_repo, new_file_contents_to_commit, commit_message, pull_request.branch_name)
                except Exception as e:
                    logger.info(f"Error in updating file{e}")
                    raise e
                total_edit_attempts += 1
                if total_edit_attempts >= GHA_MAX_EDIT_ATTEMPTS:
                    logger.info(f"Tried to edit PR {GHA_MAX_EDIT_ATTEMPTS} times, giving up.")
                    break