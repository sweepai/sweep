"""
on_ticket is the main function that is called when a new issue is created.
It is only called by the webhook handler in sweepai/api.py.
"""

import copy
import os
import traceback
from time import time

from github import BadCredentialsException
from github.WorkflowRun import WorkflowRun
from github.PullRequest import PullRequest as GithubPullRequest
from loguru import logger


from sweepai.chat.api import posthog_trace
from sweepai.core.context_pruning import RepoContextManager
from sweepai.core.sweep_bot import GHA_PROMPT
from sweepai.agents.image_description_bot import ImageDescriptionBot
from sweepai.config.client import (
    RESET_FILE,
    REVERT_CHANGED_FILES_TITLE,
    SweepConfig,
    get_gha_enabled,
)
from sweepai.config.server import (
    DEPLOYMENT_GHA_ENABLED,
    ENV,
    GITHUB_LABEL_NAME,
    IS_SELF_HOSTED,
    MONGODB_URI,
)
from sweepai.core.entities import (
    MockPR,
    NoFilesException,
    PullRequest,
)
from sweepai.core.pr_reader import PRReader
from sweepai.core.sweep_bot import get_files_to_change, get_files_to_change_for_gha, validate_file_change_requests
from sweepai.handlers.on_failing_github_actions import on_failing_github_actions
from sweepai.handlers.create_pr import (
    handle_file_change_requests,
)
from sweepai.utils.image_utils import get_image_contents_from_urls, get_image_urls_from_issue
from sweepai.utils.issue_validator import validate_issue
from sweepai.utils.prompt_constructor import get_issue_request
from sweepai.utils.ticket_rendering_utils import add_emoji, process_summary, remove_emoji, get_payment_messages, get_comment_header, render_fcrs, send_email_to_user, get_failing_gha_logs, rewrite_pr_description, raise_on_no_file_change_requests, get_branch_diff_text, handle_empty_repository, delete_old_prs
from sweepai.utils.validate_license import validate_license
from sweepai.utils.buttons import Button, ButtonList
from sweepai.utils.chat_logger import ChatLogger
from sentry_sdk import set_user
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import (
    CURRENT_USERNAME,
    ClonedRepo,
    commit_multi_file_changes,
    convert_pr_draft_field,
    create_branch,
    get_github_client,
    refresh_token,
    sanitize_string_for_github,
    validate_and_sanitize_multi_file_changes,
)
from sweepai.utils.slack_utils import add_slack_context
from sweepai.utils.str_utils import (
    BOT_SUFFIX,
    FASTER_MODEL_MESSAGE,
    blockquote,
    bold,
    bot_suffix,
    create_collapsible,
    discord_suffix,
    get_hash,
    strip_sweep,
    to_branch_name,
)
from sweepai.utils.ticket_utils import (
    center,
    fetch_relevant_files,
    fire_and_forget_wrapper,
    prep_snippets,
)

@posthog_trace
def on_ticket(
    username: str,
    title: str,
    summary: str,
    issue_number: int,
    issue_url: str, # purely for logging purposes
    repo_full_name: str,
    repo_description: str,
    installation_id: int,
    comment_id: int = None,
    edited: bool = False,
    tracking_id: str | None = None,
):
    set_user({"username": username})
    if not os.environ.get("CLI"):
        assert validate_license(), "License key is invalid or expired. Please contact us at team@sweep.dev to upgrade to an enterprise license."
    with logger.contextualize(
        tracking_id=tracking_id,
    ):
        if tracking_id is None:
            tracking_id = get_hash()
        on_ticket_start_time = time()
        logger.info(f"Starting on_ticket with title {title} and summary {summary}")
        (
            title,
            slow_mode,
            do_map,
            subissues_mode,
            sandbox_mode,
            fast_mode,
            lint_mode,
        ) = strip_sweep(title)
        summary, repo_name, user_token, g, repo, current_issue, assignee, overrided_branch_name = process_summary(summary, issue_number, repo_full_name, installation_id)

        chat_logger: ChatLogger = (
            ChatLogger(
                {
                    "repo_name": repo_name,
                    "title": title,
                    "summary": summary,
                    "issue_number": issue_number,
                    "issue_url": issue_url,
                    "username": (
                        username if not username.startswith("sweep") else assignee
                    ),
                    "repo_full_name": repo_full_name,
                    "repo_description": repo_description,
                    "installation_id": installation_id,
                    "type": "ticket",
                    "mode": ENV,
                    "comment_id": comment_id,
                    "edited": edited,
                    "tracking_id": tracking_id,
                },
                active=True,
            )
            if MONGODB_URI
            else None
        )

        if chat_logger and not IS_SELF_HOSTED:
            is_paying_user = chat_logger.is_paying_user()
            use_faster_model = chat_logger.use_faster_model()
        else:
            is_paying_user = True
            use_faster_model = False

        if use_faster_model:
            raise Exception(FASTER_MODEL_MESSAGE)

        if fast_mode:
            use_faster_model = True

        if not comment_id and not edited and chat_logger and not sandbox_mode:
            fire_and_forget_wrapper(chat_logger.add_successful_ticket)(
                gpt3=use_faster_model
            )

        organization, repo_name = repo_full_name.split("/")
        metadata = {
            "issue_url": issue_url,
            "repo_full_name": repo_full_name,
            "organization": organization,
            "repo_name": repo_name,
            "repo_description": repo_description,
            "username": username,
            "comment_id": comment_id,
            "title": title,
            "installation_id": installation_id,
            "function": "on_ticket",
            "edited": edited,
            "model": "gpt-3.5" if use_faster_model else "gpt-4",
            "tier": "pro" if is_paying_user else "free",
            "mode": ENV,
            "slow_mode": slow_mode,
            "do_map": do_map,
            "subissues_mode": subissues_mode,
            "sandbox_mode": sandbox_mode,
            "fast_mode": fast_mode,
            "is_self_hosted": IS_SELF_HOSTED,
            "tracking_id": tracking_id,
        }
        fire_and_forget_wrapper(posthog.capture)(
            username, "started", properties=metadata
        )

        try:
            if current_issue.state == "closed":
                fire_and_forget_wrapper(posthog.capture)(
                    username,
                    "issue_closed",
                    properties={
                        **metadata,
                        "duration": round(time() - on_ticket_start_time),
                    },
                )
                return {"success": False, "reason": "Issue is closed"}

            fire_and_forget_wrapper(add_emoji)(current_issue, comment_id)
            fire_and_forget_wrapper(remove_emoji)(
                current_issue, comment_id, content_to_delete="rocket"
            )
            fire_and_forget_wrapper(remove_emoji)(
                current_issue, comment_id, content_to_delete="confused"
            )
            fire_and_forget_wrapper(current_issue.edit)(body=summary)

            replies_text = ""
            summary = summary if summary else ""

            fire_and_forget_wrapper(delete_old_prs)(repo, issue_number)

            progress_headers = [
                None,
                "Step 1: 🔎 Searching",
                "Step 2: ⌨️ Coding",
                "Step 3: 🔄️ Validating",
            ]

            issue_comment = None
            payment_message, payment_message_start = get_payment_messages(
                chat_logger
            )

            config_pr_url = None
            cloned_repo: ClonedRepo = ClonedRepo(
                repo_full_name,
                installation_id=installation_id,
                token=user_token,
                repo=repo,
                branch=overrided_branch_name,
            )
            # check that repo's directory is non-empty
            if os.listdir(cloned_repo.cached_dir) == []:
                handle_empty_repository(comment_id, current_issue, progress_headers, issue_comment)
                return {"success": False}
            indexing_message = (
                "I'm searching for relevant snippets in your repository. If this is your first"
                " time using Sweep, I'm indexing your repository, which will take a few minutes."
            )
            first_comment = (
                f"{get_comment_header(0, g, repo_full_name, progress_headers, tracking_id, payment_message_start)}\n## "
                f"{progress_headers[1]}\n{indexing_message}{bot_suffix}{discord_suffix}"
            )
            # Find Sweep's previous comment
            comments = []
            for comment in current_issue.get_comments():
                comments.append(comment)
                if comment.user.login == CURRENT_USERNAME:
                    issue_comment = comment
                    break
            if issue_comment is None:
                issue_comment = current_issue.create_comment(first_comment)
            else:
                fire_and_forget_wrapper(issue_comment.edit)(first_comment)
            old_edit = issue_comment.edit
            issue_comment.edit = lambda msg: old_edit(msg + BOT_SUFFIX)
            past_messages = {}
            current_index = 0
            initial_sandbox_response = -1
            initial_sandbox_response_file = None

            def edit_sweep_comment(
                message: str,
                index: int,
                pr_message="",
                done=False,
                add_bonus_message=True,
            ):
                nonlocal current_index, user_token, g, repo, issue_comment, initial_sandbox_response, initial_sandbox_response_file
                message = sanitize_string_for_github(message)
                if pr_message:
                    pr_message = sanitize_string_for_github(pr_message)
                # -1 = error, -2 = retry
                # Only update the progress bar if the issue generation errors.
                errored = index == -1
                if index >= 0:
                    past_messages[index] = message
                    current_index = index

                agg_message = None
                # Include progress history
                # index = -2 is reserved for
                for i in range(
                    current_index + 2
                ):  # go to next header (for Working on it... text)
                    if i == 0 or i >= len(progress_headers):
                        continue  # skip None header
                    header = progress_headers[i]
                    if header is not None:
                        header = "## " + header + "\n"
                    else:
                        header = "No header\n"
                    msg = header + (past_messages.get(i) or "Working on it...")
                    if agg_message is None:
                        agg_message = msg
                    else:
                        agg_message = agg_message + "\n" + msg

                suffix = bot_suffix + discord_suffix
                if errored:
                    agg_message = (
                        "## ❌ Unable to Complete PR"
                        + "\n"
                        + message
                        + (
                            "\n\nFor bonus Sweep issues, please report this bug on our"
                            f" **[community forum](https://community.sweep.dev/)** (tracking ID: `{tracking_id}`)."
                            if add_bonus_message
                            else ""
                        )
                    )
                    suffix = bot_suffix  # don't include discord suffix for error messages

                # Update the issue comment
                msg = f"""{get_comment_header(
                    current_index, 
                    g, 
                    repo_full_name,
                    progress_headers,
                    tracking_id,
                    payment_message_start,
                    errored=errored,
                    pr_message=pr_message,
                    done=done,
                    initial_sandbox_response=initial_sandbox_response,
                    initial_sandbox_response_file=initial_sandbox_response_file,
                    config_pr_url=config_pr_url
                )}\n{agg_message}{suffix}"""
                try:
                    issue_comment.edit(msg)
                except BadCredentialsException:
                    logger.error(
                        f"Bad credentials, refreshing token (tracking ID: `{tracking_id}`)"
                    )
                    user_token, g = get_github_client(installation_id)
                    repo = g.get_repo(repo_full_name)

                    issue_comment = None
                    for comment in comments:
                        if comment.user.login == CURRENT_USERNAME:
                            issue_comment = comment
                    current_issue = repo.get_issue(number=issue_number)
                    if issue_comment is None:
                        issue_comment = current_issue.create_comment(msg)
                    else:
                        issue_comment = [
                            comment
                            for comment in current_issue.get_comments()
                            if comment.user.login == CURRENT_USERNAME
                        ][0]
                        issue_comment.edit(msg)

            if use_faster_model:
                edit_sweep_comment(
                    FASTER_MODEL_MESSAGE, -1, add_bonus_message=False
                )
                posthog.capture(
                    username,
                    "ran_out_of_tickets",
                    properties={
                        **metadata,
                        "duration": round(time() - on_ticket_start_time),
                    },
                )
                fire_and_forget_wrapper(add_emoji)(
                    current_issue, comment_id, reaction_content="confused"
                )
                fire_and_forget_wrapper(remove_emoji)(content_to_delete="eyes")
                return {
                    "success": False,
                    "error_message": "We deprecated supporting GPT 3.5.",
                }
            
            internal_message_summary = summary
            internal_message_summary += add_slack_context(internal_message_summary)
            error_message = validate_issue(title + internal_message_summary)
            if error_message:
                logger.warning(f"Validation error: {error_message}")
                edit_sweep_comment(
                    (
                        f"The issue was rejected with the following response:\n\n{bold(error_message)}"
                    ),
                    -1,
                )
                fire_and_forget_wrapper(add_emoji)(
                    current_issue, comment_id, reaction_content="confused"
                )
                fire_and_forget_wrapper(remove_emoji)(content_to_delete="eyes")
                posthog.capture(
                    username,
                    "invalid_issue",
                    properties={
                        **metadata,
                        "duration": round(time() - on_ticket_start_time),
                    },
                )
                return {"success": True}

            prs_extracted = PRReader.extract_prs(repo, summary)
            if prs_extracted:
                internal_message_summary += "\n\n" + prs_extracted
                edit_sweep_comment(
                    create_collapsible(
                        "I found that you mentioned the following Pull Requests that might be important:",
                        blockquote(
                            prs_extracted,
                        ),
                    ),
                    1,
                )

            try:
                # search/context manager
                logger.info("Searching for relevant snippets...")
                # fetch images from body of issue
                image_urls = get_image_urls_from_issue(issue_number, repo_full_name, installation_id)
                image_contents = get_image_contents_from_urls(image_urls)
                if image_contents: # doing it here to avoid editing the original issue
                    internal_message_summary += ImageDescriptionBot().describe_images(text=title + internal_message_summary, images=image_contents)
                
                snippets, tree, _, repo_context_manager = fetch_relevant_files(
                    cloned_repo,
                    title,
                    internal_message_summary,
                    replies_text,
                    username,
                    metadata,
                    on_ticket_start_time,
                    tracking_id,
                    is_paying_user,
                    issue_url,
                    chat_logger,
                    images=image_contents
                )
                cloned_repo = repo_context_manager.cloned_repo
                assert repo_context_manager.current_top_snippets or repo_context_manager.read_only_snippets, "No relevant files found."
            except Exception as e:
                edit_sweep_comment(
                    (
                        "It looks like an issue has occurred around fetching the files."
                        f" The exception was {str(e)}. If this error persists"
                        f" contact team@sweep.dev.\n\n> @{username}, editing this issue description to include more details will automatically make me relaunch. Please join our [community forum](https://community.sweep.dev/) for support (tracking_id={tracking_id})"
                    ),
                    -1,
                )
                raise e

            _user_token, g = get_github_client(installation_id)
            user_token, g, repo = refresh_token(repo_full_name, installation_id)
            cloned_repo.token = user_token
            repo = g.get_repo(repo_full_name)

            newline = "\n"
            edit_sweep_comment(
                "Here are the code search results. I'm now analyzing these search results to write the PR."
                + "\n\n"
                + create_collapsible(
                    "Relevant files (click to expand). Mentioned files will always appear here.",
                    "\n".join(
                        [
                            f"https://github.com/{organization}/{repo_name}/blob/{repo.get_commits()[0].sha}/{snippet.file_path}#L{max(snippet.start, 1)}-L{max(min(snippet.end, snippet.content.count(newline) - 1), 1)}\n"
                            for snippet in list(dict.fromkeys(repo_context_manager.current_top_snippets + repo_context_manager.read_only_snippets))
                        ]
                    ),
                )
                + (
                    create_collapsible(
                        "I also found that you mentioned the following Pull Requests that may be helpful:",
                        blockquote(prs_extracted),
                    )
                    if prs_extracted
                    else ""
                ),
                1
            )

            # Fetch git commit history
            if not repo_description:
                repo_description = "No description provided."

            internal_message_summary += replies_text
            issue_request = get_issue_request(title, internal_message_summary)

            try:
                newline = "\n"
                logger.info("Fetching files to modify/create...")
                renames_dict, file_change_requests, plan = get_files_to_change(
                    relevant_snippets=repo_context_manager.current_top_snippets,
                    read_only_snippets=repo_context_manager.read_only_snippets,
                    problem_statement=f"{title}\n\n{internal_message_summary}",
                    repo_name=repo_full_name,
                    cloned_repo=cloned_repo,
                    images=image_contents
                )
                raise_on_no_file_change_requests(title, summary, edit_sweep_comment, file_change_requests)

                planning_markdown = render_fcrs(file_change_requests)
                edit_sweep_comment(planning_markdown, 2)
            except Exception as e:
                logger.exception(e)
                # title and summary are defined elsewhere
                edit_sweep_comment(
                    (
                        "I'm sorry, but it looks like an error has occurred due to"
                        + f" a planning failure. The error message is {str(e)}. Feel free to add more details to the issue description"
                        + " so Sweep can better address it. Alternatively, reach out to Kevin or William for help at"
                        + " https://community.sweep.dev/."
                    ),
                    -1,
                )
                raise e

            # VALIDATION (modify)
            try:
                edit_sweep_comment(
                    "I'm currently validating your changes using parsers and linters to check for mistakes like syntax errors or undefined variables. If I see any of these errors, I will automatically fix them.",
                    3,
                )
                pull_request: PullRequest = PullRequest(
                    title="Sweep: " + title,
                    branch_name="sweep/" + to_branch_name(title),
                    content="",
                )
                logger.info("Making PR...")
                pull_request.branch_name = create_branch(
                    cloned_repo.repo, pull_request.branch_name, base_branch=overrided_branch_name
                )
                modify_files_dict, changed_file, file_change_requests = handle_file_change_requests(
                    file_change_requests=file_change_requests,
                    request=issue_request,
                    cloned_repo=cloned_repo,
                    username=username,
                    installation_id=installation_id,
                    renames_dict=renames_dict
                )
                commit_message = f"feat: Updated {len(modify_files_dict or [])} files"[:50]
                new_file_contents_to_commit = {file_path: file_data["contents"] for file_path, file_data in modify_files_dict.items()}
                previous_file_contents_to_commit = copy.deepcopy(new_file_contents_to_commit)
                new_file_contents_to_commit, files_removed = validate_and_sanitize_multi_file_changes(cloned_repo.repo, new_file_contents_to_commit, file_change_requests)
                if files_removed and username:
                    posthog.capture(
                        username,
                        "polluted_commits_error",
                        properties={
                            "old_keys": ",".join(previous_file_contents_to_commit.keys()),
                            "new_keys": ",".join(new_file_contents_to_commit.keys()) 
                        },
                    )
                commit = commit_multi_file_changes(cloned_repo, new_file_contents_to_commit, commit_message, pull_request.branch_name, renames_dict=renames_dict)
                edit_sweep_comment(
                    f"Your changes have been successfully made to the branch [`{pull_request.branch_name}`](https://github.com/{repo_full_name}/tree/{pull_request.branch_name}). I have validated these changes using a syntax checker and a linter.",
                    3,
                )
            except Exception as e:
                logger.exception(e)
                edit_sweep_comment(
                    (
                        "I'm sorry, but it looks like an error has occurred due to"
                        + f" a code validation failure. The error message is {str(e)}. Here were the changes I had planned:\n\n{planning_markdown}\n\n"
                        + "Feel free to add more details to the issue description"
                        + " so Sweep can better address it. Alternatively, reach out to Kevin or William for help at"
                        + " https://community.sweep.dev/."
                    ),
                    -1,
                )
                raise e
            else:
                try:
                    fire_and_forget_wrapper(remove_emoji)(content_to_delete="eyes")
                    fire_and_forget_wrapper(add_emoji)("rocket")
                except Exception as e:
                    logger.error(e)

            # set all fcrs without a corresponding change to be failed
            for file_change_request in file_change_requests:
                if file_change_request.status != "succeeded":
                    file_change_request.status = "failed"
                # also update all commit hashes associated with the fcr
                file_change_request.commit_hash_url = commit.html_url if commit else None
            if not file_change_requests:
                raise NoFilesException()
            changed_files = []

            # append all files that have been changed
            if modify_files_dict:
                for file_name, _ in modify_files_dict.items():
                    changed_files.append(file_name)

            # Refresh token
            try:
                current_issue = repo.get_issue(number=issue_number)
            except BadCredentialsException:
                user_token, g, repo = refresh_token(repo_full_name, installation_id)
                cloned_repo.token = user_token

            pr_changes = MockPR(
                file_count=len(modify_files_dict),
                title=pull_request.title,
                body="", # overrided later
                pr_head=pull_request.branch_name,
                base=cloned_repo.repo.get_branch(
                    SweepConfig.get_branch(cloned_repo.repo)
                ).commit,
                head=cloned_repo.repo.get_branch(pull_request.branch_name).commit,
            )
            pr_changes = rewrite_pr_description(issue_number, repo, overrided_branch_name, pull_request, pr_changes)

            change_location = f" [`{pr_changes.pr_head}`](https://github.com/{repo_full_name}/commits/{pr_changes.pr_head}).\n\n"
            review_message = (
                "Here are my self-reviews of my changes at" + change_location
            )

            fire_and_forget_wrapper(remove_emoji)(content_to_delete="eyes")

            # create draft pr, then convert to regular pr later
            pr: GithubPullRequest = repo.create_pull(
                title=pr_changes.title,
                body=pr_changes.body,
                head=pr_changes.pr_head,
                base=overrided_branch_name or SweepConfig.get_branch(repo),
                draft=False,
            )

            try:
                pr.add_to_assignees(username)
            except Exception as e:
                logger.warning(
                    f"Failed to add assignee {username}: {e}, probably a bot."
                )

            if len(changed_files) > 1:
                revert_buttons = []
                for changed_file in set(changed_files):
                    revert_buttons.append(
                        Button(label=f"{RESET_FILE} {changed_file}")
                    )
                revert_buttons_list = ButtonList(
                    buttons=revert_buttons, title=REVERT_CHANGED_FILES_TITLE
                )

                if revert_buttons:
                    pr.create_issue_comment(
                        revert_buttons_list.serialize() + BOT_SUFFIX
                    )

            # add comments before labelling
            pr.add_to_labels(GITHUB_LABEL_NAME)
            current_issue.create_reaction("rocket")
            heres_pr_message = f'<h1 align="center">🚀 Here\'s the PR! <a href="{pr.html_url}">#{pr.number}</a></h1>'
            progress_message = ''
            edit_sweep_comment(
                review_message + "\n\nSuccess! 🚀",
                4,
                pr_message=(
                    f"{center(heres_pr_message)}\n{center(progress_message)}\n{center(payment_message_start)}"
                ),
                done=True,
            )

            send_email_to_user(title, issue_number, username, repo_full_name, tracking_id, repo_name, g, file_change_requests, pr_changes, pr)

            on_failing_github_actions(
                f"{title}\n{internal_message_summary}\n{replies_text}",
                repo,
                username,
                pull_request,
                user_token,
                installation_id,
                chat_logger
            )

            # break from main for loop
            convert_pr_draft_field(pr, is_draft=False, installation_id=installation_id)

        except Exception as e:
            posthog.capture(
                username,
                "failed",
                properties={
                    **metadata,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                    "duration": round(time() - on_ticket_start_time),
                },
            )
            raise e
        posthog.capture(
            username,
            "success",
            properties={**metadata, "duration": round(time() - on_ticket_start_time)},
        )
        logger.info("on_ticket success in " + str(round(time() - on_ticket_start_time)))
        return {"success": True}