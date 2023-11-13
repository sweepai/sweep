import traceback
from sweepai.config.client import (
    RESET_FILE,
    REVERT_CHANGED_FILES_TITLE,
    SWEEP_BAD_FEEDBACK,
    SWEEP_GOOD_FEEDBACK,
    SweepConfig,
    get_documentation_dict,
)
from sweepai.config.server import DISCORD_FEEDBACK_WEBHOOK_URL
from sweepai.core.context_pruning import ContextPruning
from sweepai.core.documentation_searcher import extract_relevant_docs
from sweepai.core.entities import NoFilesException, SandboxResponse, SweepContext
from sweepai.core.external_searcher import ExternalSearcher
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.create_pr import GITHUB_LABEL_NAME, create_pr_changes
from sweepai.handlers.on_ticket import hydrate_sandbox_cache
from sweepai.logn import logger
from sweepai.utils.search_utils import search_snippets
from sweepai.utils.ticket_utils import post_process_snippets
from sweepai.utils.buttons import Button, ButtonList, create_action_buttons
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.search_utils import search_snippets
from sweepai.utils.str_utils import (
    blockquote,
    checkbox_template,
def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
    commit_history = cloned_repo.get_commit_history(username=username)
    def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
    external_results = ExternalSearcher.extract_summaries(message_summary)
    if external_results:
        message_summary += "\n\n" + external_results
    user_dict = get_documentation_dict(cloned_repo.repo)
    docs_results = ""
def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
        paths_to_keep,
        directories_to_expand,
    ) = context_pruning.prune_context(  # TODO, ignore directories
        human_message, repo=cloned_repo.repo
    )
    snippets = [
        snippet
        for snippet in snippets
        if any(
            snippet.file_path.startswith(path_to_keep) for path_to_keep in paths_to_keep
        )
    ]
    dir_obj.remove_all_not_included(paths_to_keep)
    dir_obj.expand_directory(directories_to_expand)
    tree = str(dir_obj)
def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
        human_message=human_message,
        repo=repo,
        is_reply=False,
        chat_logger=chat_logger,
def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
        not file_path.endswith(".py") for file_path in human_message.get_file_paths()
    )
    python_count = len(human_message.get_file_paths()) - non_python_count
    is_python_issue = python_count > non_python_count
    posthog.capture(
        username,
        "is_python_issue",
        properties={"is_python_issue": is_python_issue},
    )
    def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
        if isinstance(item, dict):
            response = item
            break
    def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
            file_change_request,
            changed_file,
            sandbox_response,
            commit,
            file_change_requests,
        ) = item
        if changed_file:
            changed_files.append(file_change_request.filename)
        sandbox_response: SandboxResponse | None = sandbox_response
        format_exit_code = (
            lambda exit_code: "✓" if exit_code == 0 else f"❌ (`{exit_code}`)"
        )
    pr_changes = response["pull_request"]
    def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
        buttons.append(Button(label=f"{RESET_FILE} {changed_file}"))
    revert_buttons_list = ButtonList(buttons=buttons, title=REVERT_CHANGED_FILES_TITLE)
    pr.create_issue_comment(revert_buttons_list.serialize())
    pr.add_to_labels(GITHUB_LABEL_NAME)

    sandbox_execution_comment_contents = "## Sandbox Executions\n\n" + "\n".join(
        [
            checkbox_template.format(
                check="X",
                filename=file_change_request.display_summary
                + " "
                + file_change_request.status_display,
                instructions=blockquote(
                    file_change_request.instructions_ticket_display
                ),
            )
            for file_change_request in file_change_requests
            if file_change_request.change_type == "check"
        ]
    )
def create_pull_request(file_change_requests, initial_sandbox_response, pull_request):
    pull_request = hydrate_sandbox_cache(file_change_requests, initial_sandbox_response, pull_request)
    return pull_request
    return pr
