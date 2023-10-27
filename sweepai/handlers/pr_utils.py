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

# from sandbox.sandbox_utils import Sandbox
from sweepai.handlers.create_pr import GITHUB_LABEL_NAME, create_pr_changes
from sweepai.logn import logger
from sweepai.utils.buttons import Button, ButtonList, create_action_buttons
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.search_utils import search_snippets
from sweepai.utils.str_utils import num_of_snippets_to_query
from sweepai.utils.ticket_utils import post_process_snippets


def make_pr(
    title,
    repo_description,
    summary,
    repo_full_name,
    installation_id,
    user_token,
    use_faster_model,
    username,
    chat_logger: ChatLogger,
    branch_name=None,
    rule=None,
):
    chat_logger.data["title"] = title
    _, repo_name = repo_full_name.split("/")
    # heavily copied code from on_ticket
    cloned_repo = ClonedRepo(
        repo_full_name,
        installation_id=installation_id,
        token=user_token,
        branch=branch_name,
    )
    logger.info("Fetching relevant files...")
    try:
        snippets, tree, dir_obj = search_snippets(
            cloned_repo,
            f"{title}\n{summary}",
            num_files=num_of_snippets_to_query,
        )
        assert len(snippets) > 0
    except SystemExit:
        raise SystemExit
    except Exception as e:
        trace = traceback.format_exc()
        logger.error(e)
        logger.error(trace)
    snippets = post_process_snippets(
        snippets, max_num_of_snippets=2 if use_faster_model else 5
    )
    commit_history = cloned_repo.get_commit_history(username=username)
    if not repo_description:
        repo_description = "No description provided."

    message_summary = summary
    external_results = ExternalSearcher.extract_summaries(message_summary)
    if external_results:
        message_summary += "\n\n" + external_results
    user_dict = get_documentation_dict(cloned_repo.repo)
    docs_results = ""
    try:
        docs_results = extract_relevant_docs(
            title + "\n" + message_summary, user_dict, chat_logger
        )
        if docs_results:
            message_summary += "\n\n" + docs_results
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(f"Failed to extract docs: {e}")
    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        username=username,
        repo_description=repo_description.strip(),
        title=title,
        summary=message_summary,
        snippets=snippets,
        tree=tree,
        commit_history=commit_history,
    )

    context_pruning = ContextPruning(chat_logger=chat_logger)
    (
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
    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        username=username,
        repo_description=repo_description.strip(),
        title=title,
        summary=message_summary,
        snippets=snippets,
        tree=tree,
        commit_history=commit_history,
    )

    _user_token, g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    sweep_bot = SweepBot.from_system_message_content(
        human_message=human_message,
        repo=repo,
        is_reply=False,
        chat_logger=chat_logger,
        cloned_repo=cloned_repo,
        sweep_context=SweepContext(
            issue_url="", use_faster_model=use_faster_model, token=user_token
        ),
    )

    non_python_count = sum(
        not file_path.endswith(".py") for file_path in human_message.get_file_paths()
    )
    python_count = len(human_message.get_file_paths()) - non_python_count
    is_python_issue = python_count > non_python_count
    posthog.capture(
        username,
        "is_python_issue",
        properties={"is_python_issue": is_python_issue},
    )
    file_change_requests, plan = sweep_bot.get_files_to_change(is_python_issue)
    file_change_requests = sweep_bot.validate_file_change_requests(
        file_change_requests, branch_name
    )
    pull_request = sweep_bot.generate_pull_request()
    generator = create_pr_changes(
        file_change_requests,
        pull_request,
        sweep_bot,
        username,
        installation_id,
        chat_logger=chat_logger,
        base_branch=branch_name,
    )
    response = {"error": NoFilesException()}
    changed_files = []
    for item in generator:
        if isinstance(item, dict):
            response = item
            break
        (
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
    pr_actions_message = (
        create_action_buttons(
            [
                SWEEP_GOOD_FEEDBACK,
                SWEEP_BAD_FEEDBACK,
            ],
            header="### PR Feedback (click)\n",
        )
        + "\n"
        if DISCORD_FEEDBACK_WEBHOOK_URL is not None
        else ""
    )
    rule_description = f'### I created this PR to address this rule: \n"{rule}"\n'
    pr = repo.create_pull(
        title=pr_changes.title,
        body=pr_actions_message + rule_description + pr_changes.body,
        head=pr_changes.pr_head,
        base=branch_name if branch_name else SweepConfig.get_branch(repo),
    )
    pr.add_to_assignees(username)
    buttons = []
    for changed_file in changed_files:
        buttons.append(Button(label=f"{RESET_FILE} {changed_file}"))
    revert_buttons_list = ButtonList(buttons=buttons, title=REVERT_CHANGED_FILES_TITLE)
    pr.create_issue_comment(revert_buttons_list.serialize())
    pr.add_to_labels(GITHUB_LABEL_NAME)
    return pr
