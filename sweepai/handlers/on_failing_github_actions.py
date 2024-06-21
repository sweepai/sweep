from collections import defaultdict
import copy
import re
from time import sleep, time

from github import WorkflowRun
from github.Repository import Repository
from github.PullRequest import PullRequest
from loguru import logger

from sweepai.agents.modify_utils import set_fcr_change_type
from sweepai.dataclasses.gha_fix import GHAFix
from sweepai.handlers.on_check_suite import delete_docker_images, get_failing_circleci_logs, get_failing_docker_logs
from sweepai.utils.str_utils import strip_triple_quotes
from sweepai.config.client import get_gha_enabled
from sweepai.config.server import CIRCLE_CI_PAT, DEPLOYMENT_GHA_ENABLED, DOCKER_ENABLED
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.core.pull_request_bot import GHA_SUMMARY_END, GHA_SUMMARY_START, PRSummaryBot
from sweepai.core.sweep_bot import GHA_PROMPT, GHA_PROMPT_WITH_HISTORY, get_files_to_change_for_gha
from sweepai.handlers.create_pr import handle_file_change_requests
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo, commit_multi_file_changes, get_github_client, refresh_token, validate_and_sanitize_multi_file_changes
from sweepai.utils.prompt_constructor import get_issue_request
from sweepai.utils.ticket_rendering_utils import get_branch_diff_text, get_failing_gha_logs
from sweepai.utils.ticket_utils import prep_snippets
from sweepai.utils.event_logger import posthog

gha_context_cleanup_system_prompt = """You are a skilled programmer. You will be given a set of failing GitHub Action logs. Your sole task is to extract and return only the crucial parts that will help a developer resolve the issues. 
Eliminate any unnecessary context and return verbatim the useful lines of logs."""

gha_generate_query_system_prompt = """You are a skilled programmer. You will be given a set of failing GitHub Action logs. 
Your sole task is to create a query based on the failing Github Action logs that will be used to vector search a code base in order to fetch relevant code snippets.
The retrived code snippets will then be used as context to help the next developer resolve the failing Github Action logs."""

gha_context_cleanup_user_prompt = """
# The failing Github Action logs are given below

{github_actions_logs}

ONLY RETURN THE USEFUL PARTS OF THE LOGS THAT WILL HELP A DEVELOPER RESOLVE THE ISSUES. NOTHING ELSE.
"""

gha_generate_query_user_prompt = """
# The failing Github Action logs are given below

{github_actions_logs}

# The initial task that resulted in these failing Github Action logs is given below

{issue_description}

Return your query below in the following xml tags:
<query>
{{generated query goes here. Remember that it will be used in a vector search so tailor your query with that in mind. There will not be multiple searches, this one search needs to get all the revelant code snippets for all issues}}
</query>
"""

SLEEP_DURATION_SECONDS = 5

def get_error_locations_from_error_logs(error_logs: str, cloned_repo: ClonedRepo):
    pattern = re.compile(r"^(?P<file_path>.*?)[^a-zA-Z\d]+(?P<line_num>\d+)[^a-zA-Z\d]+(?P<col_num>\d+)[^a-zA-Z\d]+(?P<error_message>.*?)$", re.MULTILINE)
    matches = list(pattern.finditer(error_logs))

    matched_files = []
    errors = defaultdict(dict)
    error_message = ""
    try:
        file_paths = cloned_repo.get_file_list()
        for match in matches:
            potential_file_path = match.group("file_path")
            line_number = match.group("line_num")
            current_error_message = match.group("error_message")
            if not any(file_path in potential_file_path
                    for file_path in file_paths):
                # include raw message if we cannot find the file
                error_message += f"{match.group(0)}\n"
                continue
            actual_file_path = [
                file_path 
                for file_path in file_paths
                if file_path in potential_file_path
            ][0]
            matched_files.append(actual_file_path)
            
            errors[actual_file_path][int(line_number)] = current_error_message # assume one error per line for now
        
        for file_path, errors_dict in errors.items():
            error_message += f"Here are the {len(errors_dict)} errors in {file_path}, each denotated by FIXME:\n```\n"
            file_contents = cloned_repo.get_file_contents(file_path)
            lines = file_contents.splitlines()
            erroring_lines = set()
            surrounding_lines = 5
            for line_number in errors_dict.keys():
                erroring_lines |= set(range(line_number - surrounding_lines, line_number + surrounding_lines))
            erroring_lines &= set(range(len(lines)))
            width = len(str(len(lines)))
            for i in sorted(list(erroring_lines)):
                if i not in erroring_lines:
                    error_message += "...\n"
                error_message += str(i + 1).ljust(width) + f" | {lines[i + 1]}"
                if i + 1 in errors_dict:
                    error_message += f"     FIXME {errors_dict[i + 1].strip()}"
                error_message += "\n"
            if len(lines) not in erroring_lines:
                error_message += "...\n"
            error_message += "```\n"
        deduped_matched_files = []
        for file_path in matched_files:
            if file_path not in deduped_matched_files:
                deduped_matched_files.append(file_path)
        if not error_message: # monkey patch because this can fail and return empty error_message, which is not what we want
            return error_logs, []
        return error_message, deduped_matched_files
    except Exception as e:
        logger.error(f"Error in getting error locations: {e}")
        return error_logs, []

def handle_failing_github_actions(
    problem_statement: str,
    failing_logs: str,
    repo: Repository,
    pull_request: PullRequest,
    user_token: str,
    username: str,
    installation_id: int,
    modify_files_dict: dict[str, dict[str, str | list[str]]] = {},
    modify_files_dict_history: list[dict[str, dict[str, str]]] = [],
    gha_history: list[str] = [],
    chat_logger: ChatLogger | None = None,
):
    # cleanup the gha logs
    chat_gpt = ChatGPT()
    chat_gpt.messages = [
        Message(role="system", content=gha_context_cleanup_system_prompt)
    ]
    formatted_gha_context_prompt = gha_context_cleanup_user_prompt.format(
        github_actions_logs=failing_logs
    )
    # we can also gate github actions fixes here
    failing_logs = chat_gpt.chat_anthropic(
        content=formatted_gha_context_prompt,
        temperature=0.2,
        use_openai=True,
    )
    failing_logs = strip_triple_quotes(failing_logs)
    # make edits to the PR
    # TODO: look into rollbacks so we don't continue adding onto errors
    cloned_repo = ClonedRepo( # reinitialize cloned_repo to avoid conflicts
        repo.full_name,
        installation_id=installation_id,
        token=user_token,
        repo=repo,
        branch=pull_request.head.ref,
    )
    failing_logs, _ = get_error_locations_from_error_logs(failing_logs, cloned_repo=cloned_repo)
    diffs = get_branch_diff_text(repo=repo, branch=pull_request.head.ref, base_branch=pull_request.base.ref)
    # problem_statement = f"{title}\n{internal_message_summary}\n{replies_text}"
    all_information_prompt = GHA_PROMPT.format(
        problem_statement=problem_statement,
        github_actions_logs=failing_logs,
        changes_made=diffs,
    )
    if gha_history:
        previous_gha_logs = gha_history[-1]
        all_information_prompt = GHA_PROMPT_WITH_HISTORY.format(
            problem_statement=problem_statement,
            current_github_actions_logs=failing_logs,
            changes_made=diffs,
            previous_github_actions_logs=previous_gha_logs,
        )
    snippets: list[Snippet] = prep_snippets(cloned_repo=cloned_repo, query=all_information_prompt, ticket_progress=None) # need to do this, can use the old query for speed
    issue_request = get_issue_request(
        "Fix the following errors to complete the user request.",
        all_information_prompt,
    )
    # only pass in top 10 relevant snippets at this point we dont really need context anymore, we are just modifying the existing files
    file_change_requests, plan = get_files_to_change_for_gha(
        relevant_snippets=snippets[:10],  # pylint: disable=unsubscriptable-object
        read_only_snippets=[],
        problem_statement=all_information_prompt,
        updated_files=modify_files_dict,
        cloned_repo=cloned_repo,
        chat_logger=chat_logger,
        use_openai=True
    )
    set_fcr_change_type(file_change_requests, cloned_repo)
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
            modify_files_dict=modify_files_dict,
            renames_dict={},
            previous_modify_files_dict=modify_files_dict_history[-1], 
            chat_logger=chat_logger
        )[:50]
    else:
        commit_message = pull_request_bot.get_commit_message(
            modify_files_dict=modify_files_dict,
            renames_dict={},
            chat_logger=chat_logger
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
        cloned_repo.repo = g.get_repo(repo.full_name)
        commit = commit_multi_file_changes(cloned_repo, new_file_contents_to_commit, commit_message, cloned_repo.branch)
        return commit
    except Exception as e:
        logger.info(f"Error in updating file{e}")
        raise e

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
    gha_start_time = time()
    modify_files_dict = {}

    repo_full_name = repo.full_name
    total_poll_attempts = 0
    total_edit_attempts = 0
    GITHUB_ACTIONS_ENABLED = get_gha_enabled(repo=repo) and DEPLOYMENT_GHA_ENABLED
    GHA_MAX_EDIT_ATTEMPTS = 10 # max number of times to edit PR
    current_commit = pull_request.head.sha

    _main_runs: list[WorkflowRun.WorkflowRun] = list(repo.get_workflow_runs(branch=repo.default_branch, head_sha=pull_request.base.sha))
    main_passing = True

    gha_fixes: list[GHAFix] = [
        GHAFix(
            suite_url=run.html_url,
            status="done",
            fix_commit_hash="",
            fix_diff="",
        )
        for run in _main_runs
        if run.conclusion == "success"
    ]

    docker_image_names = []

    try:
        # TODO: let's abstract out the polling logic for github actions because it's messy - have a function that polls inside the call
        # do not add return statements here because we delete the docker images at the end
        while GITHUB_ACTIONS_ENABLED and main_passing:
            if time() - gha_start_time > 59 * 60:
                user_token, g, repo = refresh_token(repo_full_name, installation_id)
                repo = g.get_repo(repo_full_name)
            should_exit, total_poll_attempts = poll_for_gha(total_poll_attempts)
            if should_exit:
                break
            # refresh the pr
            pull_request = repo.get_pull(pull_request.number)
            current_commit = repo.get_pull(pull_request.number).head.sha # IMPORTANT: resync PR otherwise you'll fetch old GHA runs
            # conditionally check CircleCI before you early exit
            failing_logs = get_circle_ci_logs(repo, current_commit)
            runs = list(repo.get_commit(current_commit).get_check_runs())
            suite_runs = list(repo.get_workflow_runs(branch=pull_request.head.ref, head_sha=pull_request.head.sha))
            if DOCKER_ENABLED:
                branch = pull_request.head.ref
                failing_logs, new_docker_image_names = get_failing_docker_logs(cloned_repo=ClonedRepo(repo_full_name, branch=branch, installation_id=installation_id, token=user_token, repo=repo))
                if new_docker_image_names:
                    docker_image_names.extend(new_docker_image_names)
            # if all runs have succeeded or have no result, break
            if all([run.conclusion in ["success", "skipped", None] and \
                    run.status not in ["in_progress", "waiting", "pending", "requested", "queued"] for run in runs]) and \
                    not failing_logs: # don't break if CircleCI or custom Dockerfile had failures
                logger.info("All Github Actions have succeeded or have no result.")
                break
            logger.debug(f"Run statuses: {[run.conclusion for run in runs]}")
            # if any of them have failed we retry
            # if no runs have failed, continue polling
            # if circleci has failed, don't poll and instead fix circleci
            if not any([run.conclusion == "failure" for run in runs]) and \
                not failing_logs:
                continue
            failed_runs = [run for run in suite_runs if run.conclusion == "failure"]
            if not failing_logs:
                failing_logs = get_failing_gha_logs(
                    failed_runs,
                    installation_id,
                )
            if failing_logs:
                # cleanup the gha logs
                chat_gpt = ChatGPT()
                chat_gpt.messages = [
                    Message(role="system", content=gha_context_cleanup_system_prompt)
                ]
                formatted_gha_context_prompt = gha_context_cleanup_user_prompt.format(
                    github_actions_logs=failing_logs
                )
                # we can also gate github actions fixes here
                failing_logs = chat_gpt.chat_anthropic(
                    content=formatted_gha_context_prompt,
                    temperature=0.2,
                    use_openai=True,
                )
                failing_logs = strip_triple_quotes(failing_logs)
                # make edits to the PR
                # TODO: look into rollbacks so we don't continue adding onto errors
                cloned_repo = ClonedRepo( # reinitialize cloned_repo to avoid conflicts
                    repo_full_name,
                    installation_id=installation_id,
                    token=user_token,
                    repo=repo,
                    branch=pull_request.head.ref,
                )
                failing_logs, _ = get_error_locations_from_error_logs(failing_logs, cloned_repo=cloned_repo)
                diffs = get_branch_diff_text(repo=repo, branch=pull_request.head.ref, base_branch=pull_request.base.ref)
                # problem_statement = f"{title}\n{internal_message_summary}\n{replies_text}"
                all_information_prompt = GHA_PROMPT.format(
                    problem_statement=problem_statement,
                    github_actions_logs=failing_logs,
                    changes_made=diffs,
                )
                if gha_history:
                    previous_gha_logs = gha_history[-1]
                    all_information_prompt = GHA_PROMPT_WITH_HISTORY.format(
                        problem_statement=problem_statement,
                        current_github_actions_logs=failing_logs,
                        changes_made=diffs,
                        previous_github_actions_logs=previous_gha_logs,
                    )
                snippets: list[Snippet] = prep_snippets(cloned_repo=cloned_repo, query=all_information_prompt, ticket_progress=None) # need to do this, can use the old query for speed
                issue_request = get_issue_request(
                    "Fix the following errors to complete the user request.",
                    all_information_prompt,
                )
                # only pass in top 10 relevant snippets at this point we dont really need context anymore, we are just modifying the existing files
                file_change_requests, plan = get_files_to_change_for_gha(
                    relevant_snippets=snippets[:10],  # pylint: disable=unsubscriptable-object
                    read_only_snippets=[],
                    problem_statement=all_information_prompt,
                    updated_files=modify_files_dict,
                    cloned_repo=cloned_repo,
                    chat_logger=chat_logger,
                    use_openai=True
                )
                set_fcr_change_type(file_change_requests, cloned_repo)
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
                        modify_files_dict=modify_files_dict,
                        renames_dict={},
                        previous_modify_files_dict=modify_files_dict_history[-1], 
                        chat_logger=chat_logger
                    )[:50]
                else:
                    commit_message = pull_request_bot.get_commit_message(
                        modify_files_dict=modify_files_dict,
                        renames_dict={},
                        chat_logger=chat_logger
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
                gha_history.append(failing_logs)
                if total_edit_attempts >= GHA_MAX_EDIT_ATTEMPTS:
                    logger.info(f"Tried to edit PR {GHA_MAX_EDIT_ATTEMPTS} times, giving up.")
                    break
    finally:
        if docker_image_names:
            delete_docker_images(docker_image_names=docker_image_names)

def poll_for_gha(total_poll_attempts) -> tuple[bool, int]:
    logger.info(
            f"Polling to see if Github Actions have finished... {total_poll_attempts}"
        )
    if total_poll_attempts * SLEEP_DURATION_SECONDS // 60 >= 120:
        logger.debug("Polling for Github Actions has taken too long, giving up.")
        return True, total_poll_attempts
    else:
        # wait one minute between check attempts
        total_poll_attempts += 1
        if total_poll_attempts > 1:
            sleep(SLEEP_DURATION_SECONDS)
    return False, total_poll_attempts

def get_circle_ci_logs(repo, current_commit):
    failed_circleci_logs = ""
    if CIRCLE_CI_PAT:
        try:
                # you need to poll here for CircleCI otherwise we'll see 0 GitHub Actions and incorrectly exit
                # this function polls internally
            failed_circleci_logs = get_failing_circleci_logs(
                    repo=repo,
                    current_commit=current_commit
                )
        except Exception as e:
            logger.error(f"Error in getting failing CircleCI logs: {e}")
            failed_circleci_logs = ""
    return failed_circleci_logs