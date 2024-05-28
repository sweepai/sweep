import copy
import re
from time import sleep

from github import WorkflowRun
from github.Repository import Repository
from github.PullRequest import PullRequest
from loguru import logger

from sweepai.agents.modify_utils import strip_triple_quotes
from sweepai.config.client import get_gha_enabled
from sweepai.config.server import DEPLOYMENT_GHA_ENABLED
from sweepai.core.chat import ChatGPT
from sweepai.core.context_pruning import RepoContextManager
from sweepai.core.entities import Message
from sweepai.core.pull_request_bot import PRSummaryBot
from sweepai.core.sweep_bot import GHA_PROMPT, GHA_PROMPT_WITH_HISTORY, get_files_to_change_for_gha, validate_file_change_requests
from sweepai.handlers.create_pr import handle_file_change_requests
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo, commit_multi_file_changes, get_github_client, validate_and_sanitize_multi_file_changes
from sweepai.utils.prompt_constructor import get_issue_request
from sweepai.utils.ticket_rendering_utils import get_branch_diff_text, get_failing_gha_logs
from sweepai.utils.ticket_utils import prep_snippets
from sweepai.utils.event_logger import posthog

gha_context_cleanup_system_prompt = """You are a skilled programmer. You will be given a set of failing GitHub Action logs. Your sole task is to extract and return only the crucial parts that will help a developer resolve the issues. 
Eliminate any unnecessary context and return verbatim the useful lines of logs."""

gha_context_cleanup_user_prompt = """
# The failing Github Action logs are given below

{github_actions_logs}

ONLY RETURN THE USEFUL PARTS OF THE LOGS THAT WILL HELP A DEVELOPER RESOLVE THE ISSUES. NOTHING ELSE.
"""

def get_error_locations_from_error_logs(error_logs: str, cloned_repo: ClonedRepo):
    annotated_error_logs = error_logs
    pattern = re.compile(r"^(?P<file_path>.*?)(?P<dummy_match>\b)(?P<line_num>\d+)(?P<error_message>.*?)$", re.MULTILINE)
    matches = pattern.findall(error_logs)
    matched_files = []

    file_paths = cloned_repo.get_file_list()
    for match in matches:
        formatted_error_message = ""
        potential_file_path, _, line_number, error_message = match
        if not any(file_path in potential_file_path
                   for file_path in file_paths):
            continue
        actual_file_path = [
            file_path 
            for file_path in file_paths
            if file_path in potential_file_path
        ][0]
        matched_files.append(actual_file_path)
        
        # get matching line of code
        file_contents = cloned_repo.get_file_contents(actual_file_path)
        lines = file_contents.splitlines()
        matched_line = int(line_number) - 1
        if matched_line >= len(lines):
            continue
        joined_match = "".join(match)
        formatted_error_message = f"{joined_match}\n    <code>{lines[matched_line]}</code>"
        annotated_error_logs = annotated_error_logs.replace(
            joined_match, formatted_error_message
        )
    deduped_matched_files = []
    for file_path in matched_files:
        if file_path not in deduped_matched_files:
            deduped_matched_files.append(file_path)
    return annotated_error_logs, matched_files


def on_failing_github_actions(
    problem_statement: str,
    repo: Repository,
    username: str,
    pull_request: PullRequest,
    user_token: str,
    installation_id: int,
    gha_history: list[str] = [],
    modify_files_dict_history: list[dict[str, dict[str, str]]] = [],
    chat_logger: ChatLogger | None = None,
):
    modify_files_dict = {}

    repo_full_name = repo.full_name
    total_poll_attempts = 0
    total_edit_attempts = 0
    SLEEP_DURATION_SECONDS = 5
    GITHUB_ACTIONS_ENABLED = get_gha_enabled(repo=repo) and DEPLOYMENT_GHA_ENABLED
    GHA_MAX_EDIT_ATTEMPTS = 10 # max number of times to edit PR
    current_commit = pull_request.head.sha

    _main_runs: list[WorkflowRun.WorkflowRun] = list(repo.get_workflow_runs(branch=repo.default_branch, head_sha=pull_request.base.sha))
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

            sleep(SLEEP_DURATION_SECONDS)
        # refresh the pr
        pull_request = repo.get_pull(pull_request.number)
        current_commit = repo.get_pull(pull_request.number).head.sha # IMPORTANT: resync PR otherwise you'll fetch old GHA runs
        runs = list(repo.get_commit(current_commit).get_check_runs())
        suite_runs = list(repo.get_workflow_runs(branch=pull_request.head.ref, head_sha=pull_request.head.sha))
        # if all runs have succeeded or have no result, break
        if all([run.conclusion in ["success", "skipped", None] and run.status not in ["in_progress", "waiting", "pending", "requested", "queued"] for run in runs]):
            logger.info("All Github Actions have succeeded or have no result.")
            break
        logger.debug(f"Run statuses: {[run.conclusion for run in runs]}")
        # if any of them have failed we retry
        if any([run.conclusion == "failure" for run in runs]):
            failed_runs = [run for run in suite_runs if run.conclusion == "failure"]

            failed_gha_logs = get_failing_gha_logs(
                failed_runs,
                installation_id,
            )
            if failed_gha_logs:
                # cleanup the gha logs
                chat_gpt = ChatGPT()
                chat_gpt.messages = [
                    Message(role="system", content=gha_context_cleanup_system_prompt)
                ]
                formatted_gha_context_prompt = gha_context_cleanup_user_prompt.format(
                    github_actions_logs=failed_gha_logs
                )
                # we can also gate github actions fixes here
                failed_gha_logs = chat_gpt.chat_anthropic(
                    content=formatted_gha_context_prompt,
                    temperature=0.2,
                    use_openai=True,
                )
                failed_gha_logs = strip_triple_quotes(failed_gha_logs)
                # make edits to the PR
                # TODO: look into rollbacks so we don't continue adding onto errors
                cloned_repo = ClonedRepo( # reinitialize cloned_repo to avoid conflicts
                    repo_full_name,
                    installation_id=installation_id,
                    token=user_token,
                    repo=repo,
                    branch=pull_request.head.ref,
                )
                failed_gha_logs, _ = get_error_locations_from_error_logs(failed_gha_logs, cloned_repo=cloned_repo)
                diffs = get_branch_diff_text(repo=repo, branch=pull_request.head.ref, base_branch=pull_request.base.ref)
                # problem_statement = f"{title}\n{internal_message_summary}\n{replies_text}"
                all_information_prompt = GHA_PROMPT.format(
                    problem_statement=problem_statement,
                    github_actions_logs=failed_gha_logs,
                    changes_made=diffs,
                )
                if gha_history:
                    previous_gha_logs = gha_history[-1]
                    all_information_prompt = GHA_PROMPT_WITH_HISTORY.format(
                        problem_statement=problem_statement,
                        current_github_actions_logs=failed_gha_logs,
                        changes_made=diffs,
                        previous_github_actions_logs=previous_gha_logs,
                    )
                
                repo_context_manager: RepoContextManager = prep_snippets(cloned_repo=cloned_repo, query=problem_statement.strip("\n"), ticket_progress=None) # need to do this, can use the old query for speed
                issue_request = get_issue_request(
                    "Fix the following errors to complete the user request.",
                    all_information_prompt,
                )
                # only pass in top 3 relevant snippets at this point we dont really need context anymore, we are just modifying the existing files
                file_change_requests, plan = get_files_to_change_for_gha(
                    relevant_snippets=repo_context_manager.current_top_snippets[:3],
                    read_only_snippets=repo_context_manager.read_only_snippets[:3],
                    problem_statement=all_information_prompt,
                    updated_files=modify_files_dict,
                    cloned_repo=cloned_repo,
                    chat_logger=chat_logger,
                    use_openai=True
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
                pull_request_bot = PRSummaryBot()
                if modify_files_dict_history:
                    commit_message = pull_request_bot.get_commit_message(
                        modify_files_dict, 
                        previous_modify_files_dict=modify_files_dict_history[-1], 
                        chat_logger=chat_logger
                    )[:50]
                else:
                    commit_message = pull_request_bot.get_commit_message(
                        modify_files_dict, chat_logger=chat_logger
                    )[:50]
                modify_files_dict_history.append(copy.deepcopy(modify_files_dict))
                    
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
                    # refresh access token
                    _token, g = get_github_client(installation_id)
                    cloned_repo.repo = g.get_repo(repo_full_name)
                    _commit = commit_multi_file_changes(cloned_repo, new_file_contents_to_commit, commit_message, cloned_repo.branch)
                except Exception as e:
                    logger.info(f"Error in updating file{e}")
                    raise e
                total_edit_attempts += 1
                gha_history.append(failed_gha_logs)
                if total_edit_attempts >= GHA_MAX_EDIT_ATTEMPTS:
                    logger.info(f"Tried to edit PR {GHA_MAX_EDIT_ATTEMPTS} times, giving up.")
                    break