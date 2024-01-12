"""
on_ticket is the main function that is called when a new issue is created.
It is only called by the webhook handler in sweepai/api.py.
"""

import difflib
import os
import re
import traceback
from time import time

import markdown
import openai
import yaml
import yamllint.config as yamllint_config
from github import BadCredentialsException
from github.Issue import Issue
from logtail import LogtailContext, LogtailHandler
from loguru import logger
from tabulate import tabulate
from tqdm import tqdm
from yamllint import linter

from sweepai.agents.pr_description_bot import PRDescriptionBot
from sweepai.config.client import (
    DEFAULT_RULES,
    RESET_FILE,
    RESTART_SWEEP_BUTTON,
    REVERT_CHANGED_FILES_TITLE,
    RULES_LABEL,
    RULES_TITLE,
    SWEEP_BAD_FEEDBACK,
    SWEEP_GOOD_FEEDBACK,
    SweepConfig,
    get_documentation_dict,
    get_rules,
)
from sweepai.config.server import (
    DISCORD_FEEDBACK_WEBHOOK_URL,
    ENV,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_NAME,
    IS_SELF_HOSTED,
    LOGTAIL_SOURCE_KEY,
    MONGODB_URI,
    OPENAI_USE_3_5_MODEL_ONLY,
    WHITELISTED_REPOS,
)
from sweepai.core.entities import (
    AssistantRaisedException,
    FileChangeRequest,
    MaxTokensExceeded,
    NoFilesException,
    ProposedIssue,
    PullRequest,
    SandboxResponse,
)
from sweepai.core.entities import create_error_logs as entities_create_error_logs
from sweepai.core.external_searcher import ExternalSearcher
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.create_pr import (
    create_config_pr,
    create_pr_changes,
    safe_delete_sweep_branch,
)
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from sweepai.utils.buttons import Button, ButtonList, create_action_buttons
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.diff import generate_diff
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.progress import (
    AssistantConversation,
    PaymentContext,
    TicketContext,
    TicketProgress,
    TicketProgressStatus,
)
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.str_utils import (
    BOT_SUFFIX,
    UPDATES_MESSAGE,
    blockquote,
    bot_suffix,
    checkbox_template,
    clean_logs,
    collapsible_template,
    create_checkbox,
    create_collapsible,
    discord_suffix,
    format_sandbox_success,
    get_hash,
    ordinal,
    sep,
    stars_suffix,
    strip_sweep,
    to_branch_name,
)
from sweepai.utils.ticket_utils import (
    center,
    fetch_relevant_files,
    fire_and_forget_wrapper,
    log_error,
)
from sweepai.utils.user_settings import UserSettings

# from sandbox.sandbox_utils import Sandbox


sweeping_gif = """<a href="https://github.com/sweepai/sweep"><img class="swing" src="https://raw.githubusercontent.com/sweepai/sweep/main/.assets/sweeping.gif" width="100" style="width:50px; margin-bottom:10px" alt="Sweeping"></a>"""


custom_config = """
extends: relaxed

rules:
    line-length: disable
    indentation: disable
"""

INSTRUCTIONS_FOR_REVIEW = """\
### 💡 To get Sweep to edit this pull request, you can:
* Comment below, and Sweep can edit the entire PR
* Comment on a file, Sweep will only modify the commented file
* Edit the original issue to get Sweep to recreate the PR from scratch"""

email_template = """Hey {name},
<br/><br/>
🚀 I just finished creating a pull request for your issue ({repo_full_name}#{issue_number}) at <a href="{pr_url}">{repo_full_name}#{pr_number}</a>!

<br/><br/>
You can view how I created this pull request <a href="{progress_url}">here</a>.

<h2>Summary</h2>
<blockquote>
{summary}
</blockquote>

<h2>Files Changed</h2>
<ul>
{files_changed}
</ul>

{sweeping_gif}
<br/>
Cheers,
<br/>
Sweep
<br/>"""


def on_ticket(
    title: str,
    summary: str,
    issue_number: int,
    issue_url: str,
    username: str,
    repo_full_name: str,
    repo_description: str,
    installation_id: int,
    comment_id: int = None,
    edited: bool = False,
    tracking_id: str | None = None,
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

    def initialize_logtail_context():
        context = LogtailContext()
        context.context(
            task={
                "issue_url": issue_url,
                "issue_number": issue_number,
                "repo_full_name": repo_full_name,
                "repo_description": repo_description,
                "username": username,
                "comment_id": comment_id,
                "edited": edited,
                "issue_title": title,
            }
        )
        handler = LogtailHandler(source_token=LOGTAIL_SOURCE_KEY, context=context)
        logger.add(handler)

    fire_and_forget_wrapper(initialize_logtail_context)()

    summary = summary or ""
    summary = re.sub(
        "<details (open)?>(\r)?\n<summary>Checklist</summary>.*",
        "",
        summary,
        flags=re.DOTALL,
    ).strip()
    summary = re.sub(
        "---\s+Checklist:(\r)?\n(\r)?\n- \[[ X]\].*", "", summary, flags=re.DOTALL
    ).strip()
    summary = re.sub("### Details\n\n_No response_", "", summary, flags=re.DOTALL)
    summary = re.sub("\n\n", "\n", summary, flags=re.DOTALL)

    repo_name = repo_full_name
    user_token, g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    current_issue: Issue = repo.get_issue(number=issue_number)
    assignee = current_issue.assignee.login if current_issue.assignee else None
    if assignee is None:
        assignee = current_issue.user.login

    try:
        CURRENT_USERNAME = g.get_user().login
    except:
        CURRENT_USERNAME = GITHUB_BOT_USERNAME

    ticket_progress = TicketProgress(
        tracking_id=tracking_id,
        username=username,
        context=TicketContext(
            title=title,
            description=summary,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            is_public=repo.private is False,
            start_time=time(),
        ),
    )

    branch_match = re.search(r"branch: (.*)(\n\r)?", summary)
    if branch_match:
        branch_name = branch_match.group(1)
        fire_and_forget_wrapper(SweepConfig.get_branch)(repo, branch_name)

    chat_logger = (
        ChatLogger(
            {
                "repo_name": repo_name,
                "title": title,
                "summary": summary,
                "issue_number": issue_number,
                "issue_url": issue_url,
                "username": username if not username.startswith("sweep") else assignee,
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

    if chat_logger:
        is_paying_user = chat_logger.is_paying_user()
        is_consumer_tier = chat_logger.is_consumer_tier()
        use_faster_model = OPENAI_USE_3_5_MODEL_ONLY or chat_logger.use_faster_model()
    else:
        is_paying_user = True
        is_consumer_tier = False
        use_faster_model = False

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

    fire_and_forget_wrapper(posthog.capture)(username, "started", properties=metadata)

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

        # Add :eyes: emoji to ticket
        def add_emoji(reaction_content="eyes"):
            item_to_react_to = (
                current_issue.get_comment(comment_id) if comment_id else current_issue
            )
            item_to_react_to.create_reaction("eyes")

        fire_and_forget_wrapper(add_emoji)()

        # If SWEEP_BOT reacted to item_to_react_to with "rocket", then remove it.
        def remove_emoji(content_to_delete="eyes"):
            item_to_react_to = (
                current_issue.get_comment(comment_id) if comment_id else current_issue
            )
            reactions = item_to_react_to.get_reactions()
            for reaction in reactions:
                if (
                    reaction.content == content_to_delete
                    and reaction.user.login == CURRENT_USERNAME
                ):
                    item_to_react_to.delete_reaction(reaction.id)

        fire_and_forget_wrapper(remove_emoji)(content_to_delete="rocket")
        fire_and_forget_wrapper(current_issue.edit)(body=summary)

        replies_text = ""
        summary = summary if summary else ""

        def delete_old_prs():
            logger.info("Deleting old PRs...")
            prs = repo.get_pulls(
                state="open",
                sort="created",
                direction="desc",
                base=SweepConfig.get_branch(repo),
            )
            checked_pr_count = 0
            for pr in tqdm(prs):
                # # Check if this issue is mentioned in the PR, and pr is owned by bot
                # # This is done in create_pr, (pr_description = ...)
                if checked_pr_count >= 40:
                    break
                if (
                    pr.user.login == CURRENT_USERNAME
                    and f"Fixes #{issue_number}.\n" in pr.body
                ):
                    success = safe_delete_sweep_branch(pr, repo)
                    break
                checked_pr_count += 1

        fire_and_forget_wrapper(delete_old_prs)()

        if not sandbox_mode:
            progress_headers = [
                None,
                "Step 1: 🔎 Searching",
                "Step 2: ⌨️ Coding",
                "Step 3: 🔁 Code Review",
            ]
        else:
            progress_headers = [
                None,
                "📖 Reading File",
                "🛠️ Executing Sandbox",
            ]

        issue_comment = None
        payment_message, payment_message_start = get_payment_messages(chat_logger)

        ticket_progress.context.payment_context = PaymentContext(
            use_faster_model=use_faster_model,
            pro_user=is_paying_user,
            daily_tickets_used=chat_logger.get_ticket_count(use_date=True)
            if chat_logger
            else 0,
            monthly_tickets_used=chat_logger.get_ticket_count() if chat_logger else 0,
        )
        ticket_progress.save()

        config_pr_url = None

        user_settings = UserSettings.from_username(username=username)
        user_settings_message = user_settings.get_message()

        def get_comment_header(
            index,
            errored=False,
            pr_message="",
            done=False,
            initial_sandbox_response: int | SandboxResponse = -1,
            initial_sandbox_response_file=None,
        ):
            config_pr_message = ""
            actions_message = create_action_buttons(
                [
                    RESTART_SWEEP_BUTTON,
                ]
            )

            sandbox_execution_message = "\n\n## GitHub Actions failed\n\nThe sandbox appears to be unavailable or down.\n\n"

            if initial_sandbox_response == -1:
                sandbox_execution_message = ""
            elif initial_sandbox_response is not None:
                repo = g.get_repo(repo_full_name)
                commit_hash = repo.get_commits()[0].sha
                success = (
                    initial_sandbox_response.outputs
                    and initial_sandbox_response.success
                )
                status = "✓" if success else "X"
                sandbox_execution_message = (
                    "\n\n## GitHub Actions"
                    + status
                    + "\n\nHere are the GitHub Actions logs prior to making any changes:\n\n"
                )
                sandbox_execution_message += entities_create_error_logs(
                    f'<a href="https://github.com/{repo_full_name}/commit/{commit_hash}"><code>{commit_hash[:7]}</code></a>',
                    initial_sandbox_response,
                    initial_sandbox_response_file,
                )
                if success:
                    sandbox_execution_message += f"\n\nSandbox passed on the latest `{repo.default_branch}`, so sandbox checks will be enabled for this issue."
                else:
                    sandbox_execution_message += f"\n\nSandbox failed, so all sandbox checks will be disabled for this issue."

            if index < 0:
                index = 0
            if index == 4:
                return (
                    pr_message
                    + config_pr_message
                    + f"\n\n---\n{user_settings.get_message(completed=True)}"
                    + f"\n\n---\n{actions_message}"
                    + sandbox_execution_message
                )

            total = len(progress_headers)
            index += 1 if done else 0
            index *= 100 / total
            index = int(index)
            index = min(100, index)
            if errored:
                pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Errored&width=600' alt='{index}%' />"
                return (
                    f"{center(sweeping_gif)}<br/>{center(pbar)}\n\n"
                    + f"\n\n---\n{actions_message}"
                    + sandbox_execution_message
                )
            pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Progress&width=600' alt='{index}%' />"
            return (
                f"{center(sweeping_gif)}"
                + (
                    center(
                        f'\n\n<h2>✨ Track Sweep\'s progress on our <a href="https://progress.sweep.dev/issues/{tracking_id}">progress dashboard</a>!</h2>'
                    )
                    if not IS_SELF_HOSTED
                    else ""
                )
                + f"<br/>{center(pbar)}"
                + ("\n" + stars_suffix if index != -1 else "")
                + "\n"
                + center(payment_message_start)
                + f"\n\n---\n{user_settings_message}"
                + config_pr_message
                + f"\n\n---\n{actions_message}"
                + sandbox_execution_message
            )

        cloned_repo = ClonedRepo(
            repo_full_name, installation_id=installation_id, token=user_token, repo=repo
        )
        # check that repo's directory is non-empty
        if os.listdir(cloned_repo.cached_dir) == []:
            logger.info("Empty repo")
            first_comment = (
                "Sweep is currently not supported on empty repositories. Please add some"
                f" code to your repository and try again.\n{sep}##"
                f" {progress_headers[1]}\n{bot_suffix}{discord_suffix}"
            )
            if issue_comment is None:
                issue_comment = current_issue.create_comment(first_comment + BOT_SUFFIX)
            else:
                issue_comment.edit(first_comment + BOT_SUFFIX)
            return {"success": False}
        indexing_message = (
            "I'm searching for relevant snippets in your repository. If this is your first"
            " time using Sweep, I'm indexing your repository. You can monitor the progress using the progress dashboard"
        )
        first_comment = (
            f"{get_comment_header(0)}\n{sep}I am currently looking into this ticket! I"
            " will update the progress of the ticket in this comment. I am currently"
            f" searching through your code, looking for relevant snippets.\n{sep}##"
            f" {progress_headers[1]}\n{indexing_message}{bot_suffix}{discord_suffix}"
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
        table = None
        initial_sandbox_response = -1
        initial_sandbox_response_file = None

        def edit_sweep_comment(message: str, index: int, pr_message="", done=False):
            nonlocal current_index, user_token, g, repo, issue_comment, initial_sandbox_response, initial_sandbox_response_file
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
                    agg_message = agg_message + f"\n{sep}" + msg

            suffix = bot_suffix + discord_suffix
            if errored:
                agg_message = (
                    "## ❌ Unable to Complete PR"
                    + "\n"
                    + message
                    + "\n\nFor bonus GPT-4 tickets, please report this bug on"
                    f" **[Discord](https://discord.gg/invite/sweep)** (tracking ID: `{tracking_id}`)."
                )
                if table is not None:
                    agg_message = (
                        agg_message
                        + f"\n{sep}Please look at the generated plan. If something looks"
                        f" wrong, please add more details to your issue.\n\n{table}"
                    )
                suffix = bot_suffix  # don't include discord suffix for error messages

            # Update the issue comment
            msg = f"{get_comment_header(current_index, errored, pr_message, done=done, initial_sandbox_response=initial_sandbox_response, initial_sandbox_response_file=initial_sandbox_response_file)}\n{sep}{agg_message}{suffix}"
            try:
                issue_comment.edit(msg)
            except BadCredentialsException:
                logger.error(
                    f"Bad credentials, refreshing token (tracking ID: `{tracking_id}`)"
                )
                _user_token, g = get_github_client(installation_id)
                repo = g.get_repo(repo_full_name)

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

        if sandbox_mode:
            handle_sandbox_mode(
                title, repo_full_name, repo, ticket_progress, edit_sweep_comment
            )
            return {"success": True}

        if len(title + summary) < 20:
            logger.info("Issue too short")
            edit_sweep_comment(
                (
                    f"Please add more details to your issue. I need at least 20 characters"
                    f" to generate a plan. Please join our Discord server for support (tracking_id={tracking_id})"
                ),
                -1,
            )
            posthog.capture(
                username,
                "issue_too_short",
                properties={
                    **metadata,
                    "duration": round(time() - on_ticket_start_time),
                },
            )
            return {"success": True}

        if (
            repo_name.lower() not in WHITELISTED_REPOS
            and not is_paying_user
            and not is_consumer_tier
        ):
            if ("sweep" in repo_name.lower()) or ("test" in repo_name.lower()):
                logger.info("Test repository detected")
                edit_sweep_comment(
                    (
                        f"Sweep does not work on test repositories. Please create an issue"
                        f" on a real repository. If you think this is a mistake, please"
                        f" report this at https://discord.gg/sweep. Please join our Discord server for support (tracking_id={tracking_id})"
                    ),
                    -1,
                )
                posthog.capture(
                    username,
                    "test_repo",
                    properties={
                        **metadata,
                        "duration": round(time() - on_ticket_start_time),
                    },
                )
                return {"success": False}

        try:
            snippets, tree, _ = fetch_relevant_files(
                cloned_repo,
                title,
                summary,
                replies_text,
                username,
                metadata,
                on_ticket_start_time,
                tracking_id,
                is_paying_user,
                is_consumer_tier,
                issue_url,
                chat_logger,
                ticket_progress,
            )
        except:
            edit_sweep_comment(
                (
                    "It looks like an issue has occurred around fetching the files."
                    " Perhaps the repo has not been initialized. If this error persists"
                    f" contact team@sweep.dev.\n\n> @{username}, editing this issue description to include more details will automatically make me relaunch. Please join our Discord server for support (tracking_id={tracking_id})"
                ),
                -1,
            )
            raise Exception("Failed to fetch files")

        ticket_progress.search_progress.indexing_progress = (
            ticket_progress.search_progress.indexing_total
        )
        ticket_progress.status = TicketProgressStatus.PLANNING
        ticket_progress.save()

        # Fetch git commit history
        if not repo_description:
            repo_description = "No description provided."

        message_summary = summary + replies_text
        external_results = ExternalSearcher.extract_summaries(message_summary)
        if external_results:
            message_summary += "\n\n" + external_results
        user_dict = get_documentation_dict(repo)
        docs_results = ""
        human_message = HumanMessagePrompt(
            repo_name=repo_name,
            issue_url=issue_url,
            username=username,
            repo_description=repo_description.strip(),
            title=title,
            summary=message_summary,
            snippets=snippets,
            tree=tree,
        )

        _user_token, g = get_github_client(installation_id)
        repo = g.get_repo(repo_full_name)
        sweep_bot = SweepBot.from_system_message_content(
            human_message=human_message,
            repo=repo,
            is_reply=bool(comments),
            chat_logger=chat_logger,
            cloned_repo=cloned_repo,
            ticket_progress=ticket_progress,
        )

        # Check repository for sweep.yml file.
        sweep_yml_exists = False
        sweep_yml_failed = False
        for content_file in repo.get_contents(""):
            if content_file.name == "sweep.yaml":
                sweep_yml_exists = True

                # Check if YAML is valid
                yaml_content = content_file.decoded_content.decode("utf-8")
                sweep_yaml_dict = {}
                try:
                    sweep_yaml_dict = yaml.safe_load(yaml_content)
                except:
                    logger.error(f"Failed to load YAML file: {yaml_content}")
                if len(sweep_yaml_dict) > 0:
                    break
                linter_config = yamllint_config.YamlLintConfig(custom_config)
                problems = list(linter.run(yaml_content, linter_config))
                if problems:
                    errors = [
                        f"Line {problem.line}: {problem.desc} (rule: {problem.rule})"
                        for problem in problems
                    ]
                    error_message = "\n".join(errors)
                    markdown_error_message = f"**There is something wrong with your [sweep.yaml](https://github.com/{repo_full_name}/blob/main/sweep.yaml):**\n```\n{error_message}\n```"
                    sweep_yml_failed = True
                    logger.error(markdown_error_message)
                    edit_sweep_comment(markdown_error_message, -1)
                else:
                    logger.info("The YAML file is valid. No errors found.")
                break

        # If sweep.yaml does not exist, then create a new PR that simply creates the sweep.yaml file.
        if not sweep_yml_exists:
            try:
                logger.info("Creating sweep.yaml file...")
                config_pr = create_config_pr(sweep_bot, cloned_repo=cloned_repo)
                config_pr_url = config_pr.html_url
                edit_sweep_comment(message="", index=-2)
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(
                    "Failed to create new branch for sweep.yaml file.\n",
                    e,
                    traceback.format_exc(),
                )
        else:
            logger.info("sweep.yaml file already exists.")

        try:
            # ANALYZE SNIPPETS
            newline = "\n"
            edit_sweep_comment(
                "I found the following snippets in your repository. I will now analyze"
                " these snippets and come up with a plan."
                + "\n\n"
                + create_collapsible(
                    "Some code snippets I think are relevant in decreasing order of relevance (click to expand). If some file is missing from here, you can mention the path in the ticket description.",
                    "\n".join(
                        [
                            f"https://github.com/{organization}/{repo_name}/blob/{repo.get_commits()[0].sha}/{snippet.file_path}#L{max(snippet.start, 1)}-L{min(snippet.end, snippet.content.count(newline) - 1)}\n"
                            for snippet in snippets
                        ]
                    ),
                )
                + (
                    create_collapsible(
                        "I also found the following external resources that might be helpful:",
                        f"\n\n{external_results}\n\n",
                    )
                    if external_results
                    else ""
                )
                + (f"\n\n{docs_results}\n\n" if docs_results else ""),
                1,
            )

            if do_map:
                subissues: list[ProposedIssue] = sweep_bot.generate_subissues()
                edit_sweep_comment(
                    f"I'm creating the following subissues:\n\n"
                    + "\n\n".join(
                        [
                            f"#{subissue.title}:\n" + blockquote(subissue.body)
                            for subissue in subissues
                        ]
                    ),
                    2,
                )
                for subissue in tqdm(subissues):
                    subissue.issue_id = repo.create_issue(
                        title="Sweep: " + subissue.title,
                        body=subissue.body + f"\n\nParent issue: #{issue_number}",
                        assignee=username,
                    ).number
                subissues_checklist = "\n\n".join(
                    [
                        f"- [ ] #{subissue.issue_id}\n\n"
                        + blockquote(f"**{subissue.title}**\n{subissue.body}")
                        for subissue in subissues
                    ]
                )
                current_issue.edit(
                    body=summary + "\n\n---\n\nChecklist:\n\n" + subissues_checklist
                )
                edit_sweep_comment(
                    f"I finished creating the subissues! Track them at:\n\n"
                    + "\n".join(f"* #{subissue.issue_id}" for subissue in subissues),
                    3,
                    done=True,
                )
                edit_sweep_comment(f"N/A", 4)
                edit_sweep_comment(f"I finished creating all the subissues.", 5)
                posthog.capture(
                    username,
                    "subissues_created",
                    properties={
                        **metadata,
                        "count": len(subissues),
                        "duration": round(time() - on_ticket_start_time),
                    },
                )
                return {"success": True}

            logger.info("Fetching files to modify/create...")
            non_python_count = sum(
                not file_path.endswith(".py")
                and not file_path.endswith(".ipynb")
                and not file_path.endswith(".md")
                for file_path in human_message.get_file_paths()
            )
            python_count = len(human_message.get_file_paths()) - non_python_count
            is_python_issue = python_count >= non_python_count and python_count > 0
            posthog.capture(
                username,
                "is_python_issue",
                properties={"is_python_issue": is_python_issue},
            )
            file_change_requests, plan = sweep_bot.get_files_to_change(is_python_issue)
            ticket_progress.planning_progress.file_change_requests = (
                file_change_requests
            )
            ticket_progress.coding_progress.file_change_requests = file_change_requests
            ticket_progress.coding_progress.assistant_conversations = [
                AssistantConversation() for fcr in file_change_requests
            ]
            ticket_progress.save()
            ticket_progress.wait()
            ticket_progress.refresh()
            file_change_requests = (
                ticket_progress.planning_progress.file_change_requests
            )
            file_change_requests = sweep_bot.validate_file_change_requests(
                file_change_requests
            )
            ticket_progress.planning_progress.file_change_requests = (
                file_change_requests
            )
            ticket_progress.coding_progress.file_change_requests = file_change_requests
            ticket_progress.status = TicketProgressStatus.CODING
            ticket_progress.save()

            if not file_change_requests:
                if len(title + summary) < 60:
                    edit_sweep_comment(
                        (
                            "Sorry, I could not find any files to modify, can you please"
                            " provide more details? Please make sure that the title and"
                            " summary of the issue are at least 60 characters."
                        ),
                        -1,
                    )
                else:
                    edit_sweep_comment(
                        (
                            "Sorry, I could not find any files to modify, can you please"
                            " provide more details?"
                        ),
                        -1,
                    )
                raise Exception("No files to modify.")

            (
                initial_sandbox_response,
                initial_sandbox_response_file,
            ) = sweep_bot.validate_sandbox(file_change_requests)

            file_change_requests: list[
                FileChangeRequest
            ] = sweep_bot.validate_file_change_requests(
                file_change_requests, initial_sandbox_response=initial_sandbox_response
            )
            ticket_progress.planning_progress.file_change_requests = (
                file_change_requests
            )
            ticket_progress.coding_progress.assistant_conversations = [
                AssistantConversation() for fcr in file_change_requests
            ]
            ticket_progress.save()

            table = tabulate(
                [
                    [
                        file_change_request.entity_display,
                        file_change_request.instructions_display.replace(
                            "\n", "<br/>"
                        ).replace("```", "\\```"),
                    ]
                    for file_change_request in file_change_requests
                    if file_change_request.change_type != "check"
                ],
                headers=["File Path", "Proposed Changes"],
                tablefmt="pipe",
            )

            logger.info("Generating PR...")

            pull_request = PullRequest(
                title="Sweep: " + title,
                branch_name="sweep/" + to_branch_name(title),
                content="",
            )
            logger.info("Making PR...")

            ticket_progress.context.branch_name = pull_request.branch_name
            ticket_progress.save()

            files_progress: list[tuple[str, str, str, str]] = [
                (
                    file_change_request.entity_display,
                    file_change_request.instructions_display,
                    "⏳ In Progress",
                    "",
                )
                for file_change_request in file_change_requests
            ]

            checkboxes_progress: list[tuple[str, str, str]] = [
                (
                    file_change_request.entity_display,
                    file_change_request.instructions_display,
                    " ",
                )
                for file_change_request in file_change_requests
                if not file_change_request.change_type == "check"
            ]
            checkboxes_contents = "\n".join(
                [
                    create_checkbox(
                        f"`{filename}`", blockquote(instructions), check == "X"
                    )
                    for filename, instructions, check in checkboxes_progress
                ]
            )
            checkboxes_collapsible = create_collapsible(
                "Checklist", checkboxes_contents, opened=True
            )

            file_change_requests[0].status = "running"

            condensed_checkboxes_contents = "\n".join(
                [
                    create_checkbox(f"`{filename}`", "", check == "X").strip()
                    for filename, instructions, check in checkboxes_progress
                ]
            )
            condensed_checkboxes_collapsible = create_collapsible(
                "Checklist", condensed_checkboxes_contents, opened=True
            )

            current_issue = repo.get_issue(number=issue_number)
            current_issue.edit(body=summary + "\n\n" + condensed_checkboxes_collapsible)

            delete_branch = False

            generator = create_pr_changes(
                file_change_requests,
                pull_request,
                sweep_bot,
                username,
                installation_id,
                issue_number,
                chat_logger=chat_logger,
            )
            edit_sweep_comment(checkboxes_contents, 2)
            response = {"error": NoFilesException()}

            def create_error_logs(
                commit_url_display: str,
                sandbox_response: SandboxResponse,
                status: str = "✓",
            ):
                return (
                    (
                        "<br/>"
                        + create_collapsible(
                            f"Sandbox logs for {commit_url_display} {status}",
                            blockquote(
                                "\n\n".join(
                                    [
                                        create_collapsible(
                                            f"<code>{output}</code> {i + 1}/{len(sandbox_response.outputs)} {format_sandbox_success(sandbox_response.success)}",
                                            f"<pre>{clean_logs(output)}</pre>",
                                            i == len(sandbox_response.outputs) - 1,
                                        )
                                        for i, output in enumerate(
                                            sandbox_response.outputs
                                        )
                                        if len(sandbox_response.outputs) > 0
                                    ]
                                )
                            ),
                            opened=True,
                        )
                    )
                    if sandbox_response
                    else ""
                )

            def update_progress(
                entity_display: str,
                header: str,
                error_logs: str,
                status: str = "X",
            ):
                nonlocal checkboxes_progress
                for i, (entity_display_, instructions, status_) in enumerate(
                    checkboxes_progress
                ):
                    if entity_display in entity_display_:
                        checkboxes_progress[i] = (
                            header,
                            instructions + error_logs,
                            status,
                        )
                        return True
                return False

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
                changed_files.append(file_change_request.filename)
                sandbox_response: SandboxResponse | None = sandbox_response
                logger.info(sandbox_response)
                commit_hash: str = (
                    commit
                    if isinstance(commit, str)
                    else (
                        commit.sha
                        if commit is not None
                        else repo.get_branch(pull_request.branch_name).commit.sha
                    )
                )
                commit_url = f"https://github.com/{repo_full_name}/commit/{commit_hash}"
                commit_url_display = (
                    f"<a href='{commit_url}'><code>{commit_hash[:7]}</code></a>"
                )
                error_logs: str = create_error_logs(
                    commit_url_display,
                    sandbox_response,
                    status="✓"
                    if (sandbox_response is None or sandbox_response.success)
                    else "❌",
                )
                checkboxes_progress = [
                    (
                        file_change_request.display_summary
                        + " "
                        + file_change_request.status_display
                        + " "
                        + (file_change_request.commit_hash_url or "")
                        + f" [Edit]({file_change_request.get_edit_url(repo.full_name, pull_request.branch_name)})",
                        file_change_request.instructions_ticket_display
                        + f"\n\n{file_change_request.diff_display}",
                        "X"
                        if file_change_request.status in ("succeeded", "failed")
                        else " ",
                    )
                    for file_change_request in file_change_requests
                ]
                checkboxes_contents = "\n".join(
                    [
                        checkbox_template.format(
                            check=check,
                            filename=filename,
                            instructions=blockquote(instructions),
                        )
                        for filename, instructions, check in checkboxes_progress
                    ]
                )
                checkboxes_collapsible = collapsible_template.format(
                    summary="Checklist",
                    body=checkboxes_contents,
                    opened="open",
                )
                condensed_checkboxes_contents = "\n".join(
                    [
                        checkbox_template.format(
                            check=check,
                            filename=filename,
                            instructions="",
                        ).strip()
                        for filename, instructions, check in checkboxes_progress
                        if not instructions.lower().startswith("run")
                    ]
                )
                condensed_checkboxes_collapsible = collapsible_template.format(
                    summary="Checklist",
                    body=condensed_checkboxes_contents,
                    opened="open",
                )

                current_issue = repo.get_issue(number=issue_number)
                current_issue.edit(
                    body=summary + "\n\n" + condensed_checkboxes_collapsible
                )

                logger.info(files_progress)
                logger.info(f"Edited {file_change_request.entity_display}")
                edit_sweep_comment(checkboxes_contents, 2)
            if not response.get("success"):
                raise Exception(f"Failed to create PR: {response.get('error')}")

            checkboxes_contents = "\n".join(
                [
                    checkbox_template.format(
                        check=check,
                        filename=filename,
                        instructions=blockquote(instructions),
                    )
                    for filename, instructions, check in checkboxes_progress
                ]
            )
            condensed_checkboxes_contents = "\n".join(
                [
                    checkbox_template.format(
                        check=check,
                        filename=filename,
                        instructions="",
                    ).strip()
                    for filename, instructions, check in checkboxes_progress
                    if not instructions.lower().startswith("run")
                ]
            )
            condensed_checkboxes_collapsible = collapsible_template.format(
                summary="Checklist",
                body=condensed_checkboxes_contents,
                opened="open",
            )
            for _ in range(3):
                try:
                    current_issue.edit(
                        body=summary + "\n\n" + condensed_checkboxes_collapsible
                    )
                    break
                except:
                    from time import sleep

                    sleep(1)
            edit_sweep_comment(checkboxes_contents, 2)

            pr_changes = response["pull_request"]
            # change the body here
            diff_text = get_branch_diff_text(repo, pull_request.branch_name)
            new_description = PRDescriptionBot().describe_diffs(
                diff_text,
                pull_request.title,
            )
            # TODO: update the title as well
            if new_description:
                pr_changes.body = (
                    f"{new_description}\n\nFixes"
                    f" #{issue_number}.\n\n---\n\n{UPDATES_MESSAGE}\n\n---\n\n{INSTRUCTIONS_FOR_REVIEW}"
                )

            edit_sweep_comment(
                "I have finished coding the issue. I am now reviewing it for completeness.",
                3,
            )
            change_location = f" [`{pr_changes.pr_head}`](https://github.com/{repo_full_name}/commits/{pr_changes.pr_head}).\n\n"
            review_message = (
                "Here are my self-reviews of my changes at" + change_location
            )

            lint_output = None
            try:
                fire_and_forget_wrapper(remove_emoji)(content_to_delete="eyes")
            except SystemExit:
                raise SystemExit
            except:
                pass

            changes_required, review_message = False, ""
            if False:
                changes_required, review_message = review_code(
                    repo,
                    pr_changes,
                    issue_url,
                    username,
                    repo_description,
                    title,
                    summary,
                    replies_text,
                    tree,
                    lint_output,
                    plan,
                    chat_logger,
                    review_message,
                    edit_sweep_comment,
                    repo_full_name,
                    installation_id,
                )

            if changes_required:
                edit_sweep_comment(
                    review_message + "\n\nI finished incorporating these changes.",
                    3,
                )
            else:
                edit_sweep_comment(
                    f"I have finished reviewing the code for completeness. I did not find errors for {change_location}",
                    3,
                )

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
            revert_buttons = []
            for changed_file in set(changed_files):
                revert_buttons.append(Button(label=f"{RESET_FILE} {changed_file}"))
            revert_buttons_list = ButtonList(
                buttons=revert_buttons, title=REVERT_CHANGED_FILES_TITLE
            )

            rule_buttons = []
            repo_rules = get_rules(repo)
            if repo_rules != [""]:
                for rule in repo_rules:
                    if rule:
                        rule_buttons.append(Button(label=f"{RULES_LABEL} {rule}"))
                if len(repo_rules) == 0:
                    for rule in DEFAULT_RULES:
                        rule_buttons.append(Button(label=f"{RULES_LABEL} {rule}"))

            rules_buttons_list = ButtonList(buttons=rule_buttons, title=RULES_TITLE)

            sandbox_passed = None
            for file_change_request in file_change_requests:
                if file_change_request.change_type == "check":
                    if (
                        file_change_request.sandbox_response
                        and file_change_request.sandbox_response.error_messages
                    ):
                        sandbox_passed = False
                    elif sandbox_passed is None:
                        sandbox_passed = True

            if sandbox_passed == True:
                pr_changes.title = f"{pr_changes.title} (✓ Sandbox Passed)"

            # delete failing sweep yaml if applicable
            if sweep_yml_failed:
                try:
                    repo.delete_file(
                        "sweep.yaml",
                        "Delete failing sweep.yaml",
                        branch=pr_changes.pr_head,
                        sha=repo.get_contents("sweep.yaml").sha,
                    )
                except:
                    pass

            pr: PullRequest = repo.create_pull(
                title=pr_changes.title,
                body=pr_actions_message + pr_changes.body,
                head=pr_changes.pr_head,
                base=SweepConfig.get_branch(repo),
            )

            ticket_progress.status = TicketProgressStatus.COMPLETE
            ticket_progress.context.done_time = time()
            ticket_progress.context.pr_id = pr.number
            ticket_progress.save()

            if revert_buttons:
                pr.create_issue_comment(revert_buttons_list.serialize() + BOT_SUFFIX)
            if rule_buttons:
                pr.create_issue_comment(rules_buttons_list.serialize() + BOT_SUFFIX)

            # add comments before labelling
            pr.add_to_labels(GITHUB_LABEL_NAME)
            current_issue.create_reaction("rocket")
            heres_pr_message = f'<h1 align="center">🚀 Here\'s the PR! <a href="{pr.html_url}">#{pr.number}</a></h1>'
            progress_message = f'<div align="center"><b>See Sweep\'s progress at <a href="https://progress.sweep.dev/issues/{tracking_id}">the progress dashboard</a>!</b></div>'
            edit_sweep_comment(
                review_message + "\n\nSuccess! 🚀",
                4,
                pr_message=(
                    f"{center(heres_pr_message)}\n{center(progress_message)}\n{center(payment_message_start)}"
                ),
                done=True,
            )

            user_settings = UserSettings.from_username(username=username)
            user = g.get_user(username)
            full_name = user.name or user.login
            name = full_name.split(" ")[0]
            files_changed = []
            for fcr in file_change_requests:
                if fcr.change_type in ("create", "modify"):
                    diff = list(
                        difflib.unified_diff(
                            (fcr.old_content or "").splitlines() or [],
                            (fcr.new_content or "").splitlines() or [],
                            lineterm="",
                        )
                    )
                    added = sum(
                        1
                        for line in diff
                        if line.startswith("+") and not line.startswith("+++")
                    )
                    removed = sum(
                        1
                        for line in diff
                        if line.startswith("-") and not line.startswith("---")
                    )
            # Install Sweep Configs: Pull Request
            if config_pr_url is not None:
                files_changed.append(
                    f"Install Sweep Configs: <a href='{config_pr_url}'>Pull Request</a>" 
                )
            files_changed.append(
                f"<code>{fcr.filename}</code> (+{added}/-{removed})"
            )
            user_settings.send_email(
                subject=f"Sweep Pull Request Complete for {repo_name}#{issue_number} {title}",
                html=email_template.format(
                    name=name,
                    pr_url=pr.html_url,
                    issue_number=issue_number,
                    repo_full_name=repo_full_name,
                    pr_number=pr.number,
                    progress_url=f"https://progress.sweep.dev/issues/{tracking_id}",
                    summary=markdown.markdown(pr_changes.body),
                    files_changed="\n".join(
                        [f"<li>{item}</li>" for item in files_changed]
                    ),
                    sweeping_gif=sweeping_gif,
                ),
            )
        except MaxTokensExceeded as e:
            logger.info("Max tokens exceeded")
            ticket_progress.status = TicketProgressStatus.ERROR
            ticket_progress.error_message = "Max tokens exceeded. Feel free to add more details to the issue descript for Sweep to better address it, or alternatively, reach out to Kevin or William for help at https://discord.gg/sweep."
            ticket_progress.save()
            log_error(
                is_paying_user,
                is_consumer_tier,
                username,
                issue_url,
                "Max Tokens Exceeded",
                str(e) + "\n" + traceback.format_exc(),
                priority=2,
            )
            if chat_logger and chat_logger.is_paying_user():
                edit_sweep_comment(
                    (
                        f"Sorry, I could not edit `{e.filename}` as this file is too long."
                        " We are currently working on improved file streaming to address"
                        " this issue.\n"
                    ),
                    -1,
                )
            else:
                edit_sweep_comment(
                    (
                        f"Sorry, I could not edit `{e.filename}` as this file is too"
                        " long.\n\nIf this file is incorrect, please describe the desired"
                        " file in the prompt. However, if you would like to edit longer"
                        " files, consider upgrading to [Sweep Pro](https://sweep.dev/) for"
                        " longer context lengths.\n"
                    ),
                    -1,
                )
            delete_branch = True
            raise e
        except NoFilesException as e:
            ticket_progress.status = TicketProgressStatus.ERROR
            ticket_progress.error_message = "Sweep could not find files to modify to address this issue. Feel free to add more details to the issue descript for Sweep to better address it, or alternatively, reach out to Kevin or William for help at https://discord.gg/sweep."
            ticket_progress.save()

            logger.info("Sweep could not find files to modify")
            log_error(
                is_paying_user,
                is_consumer_tier,
                username,
                issue_url,
                "Sweep could not find files to modify",
                str(e) + "\n" + traceback.format_exc(),
                priority=2,
            )
            edit_sweep_comment(
                (
                    "Sorry, Sweep could not find any appropriate files to edit to address"
                    " this issue. If this is a mistake, please provide more context and Sweep"
                    f" will retry!\n\n> @{username}, please edit the issue description to"
                    " include more details about this issue."
                ),
                -1,
            )
            delete_branch = True
            raise e
        except openai.BadRequestError as e:
            ticket_progress.status = TicketProgressStatus.ERROR
            ticket_progress.error_message = "Sorry, it looks like there is an error with communicating with OpenAI. If this error persists, reach out to Kevin or William for help at https://discord.gg/sweep."
            ticket_progress.save()

            logger.error(traceback.format_exc())
            logger.error(e)
            edit_sweep_comment(
                (
                    "I'm sorry, but it looks our model has ran out of context length. We're"
                    " trying to make this happen less, but one way to mitigate this is to"
                    " code smaller files. If this error persists report it at"
                    " https://discord.gg/sweep."
                ),
                -1,
            )
            log_error(
                is_paying_user,
                is_consumer_tier,
                username,
                issue_url,
                "Context Length",
                str(e) + "\n" + traceback.format_exc(),
                priority=2,
            )
            posthog.capture(
                username,
                "failed",
                properties={
                    "error": str(e),
                    "trace": traceback.format_exc(),
                    "reason": "Invalid request error / context length",
                    **metadata,
                    "duration": round(time() - on_ticket_start_time),
                },
            )
            delete_branch = True
            raise e
        except AssistantRaisedException as e:
            ticket_progress.status = TicketProgressStatus.ERROR
            ticket_progress.error_message = f"Sweep raised an error with the following message: {e.message}. Feel free to add more details to the issue descript for Sweep to better address it, or alternatively, reach out to Kevin or William for help at https://discord.gg/sweep."
            ticket_progress.save()

            logger.exception(e)
            edit_sweep_comment(
                f"Sweep raised an error with the following message:\n{blockquote(e.message)}",
                -1,
            )
            log_error(
                is_paying_user,
                is_consumer_tier,
                username,
                issue_url,
                "Workflow",
                str(e) + "\n" + traceback.format_exc(),
                priority=1,
            )
            raise e
        except Exception as e:
            ticket_progress.status = TicketProgressStatus.ERROR
            ticket_progress.error_message = f"Internal server error: {str(e)}. Feel free to add more details to the issue descript for Sweep to better address it, or alternatively, reach out to Kevin or William for help at https://discord.gg/sweep."
            ticket_progress.save()

            logger.error(traceback.format_exc())
            logger.error(e)
            # title and summary are defined elsewhere
            if len(title + summary) < 60:
                edit_sweep_comment(
                    (
                        "I'm sorry, but it looks like an error has occurred due to"
                        + " a planning failure. Feel free to add more details to the issue description"
                        + " so Sweep can better address it. Alternatively, reach out to Kevin or William for help at"
                        + " https://discord.gg/sweep."
                    ),
                    -1,
                )
            else:
                edit_sweep_comment(
                    (
                        "I'm sorry, but it looks like an error has occurred due to"
                        + " a planning failure. Feel free to add more details to the issue description"
                        + " so Sweep can better address it. Alternatively, reach out to Kevin or William for help at"
                        + " https://discord.gg/sweep."
                    ),
                    -1,
                )
            log_error(
                is_paying_user,
                is_consumer_tier,
                username,
                issue_url,
                "Workflow",
                str(e) + "\n" + traceback.format_exc(),
                priority=1,
            )
            raise e
        else:
            try:
                fire_and_forget_wrapper(remove_emoji)(content_to_delete="eyes")
                fire_and_forget_wrapper(add_emoji)("rocket")
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(e)
        finally:
            cloned_repo.delete()

        if delete_branch:
            try:
                if pull_request.branch_name.startswith("sweep"):
                    repo.get_git_ref(f"heads/{pull_request.branch_name}").delete()
                else:
                    raise Exception(
                        f"Branch name {pull_request.branch_name} does not start with sweep/"
                    )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(e)
                logger.error(traceback.format_exc())
                logger.info("Deleted branch", pull_request.branch_name)
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


def handle_sandbox_mode(
    title, repo_full_name, repo, ticket_progress, edit_sweep_comment
):
    logger.info("Running in sandbox mode")
    sweep_bot = SweepBot(repo=repo, ticket_progress=ticket_progress)
    logger.info("Getting file contents")
    file_name = title.split(":")[1].strip()
    file_contents = sweep_bot.get_contents(file_name).decoded_content.decode("utf-8")
    try:
        ext = file_name.split(".")[-1]
    except:
        ext = ""
    displayed_contents = file_contents.replace("```", "\`\`\`")
    sha = repo.get_branch(repo.default_branch).commit.sha
    permalink = f"https://github.com/{repo_full_name}/blob/{sha}/{file_name}#L1-L{len(file_contents.splitlines())}"
    logger.info("Running sandbox")
    edit_sweep_comment(
        f"Running sandbox for {file_name}. Current Code:\n\n{permalink}",
        1,
    )
    updated_contents, sandbox_response = sweep_bot.check_sandbox(
        file_name, file_contents, []
    )
    logger.info("Sandbox finished")
    logs = (
        (
            "<br/>"
            + create_collapsible(
                f"Sandbox logs",
                blockquote(
                    "\n\n".join(
                        [
                            create_collapsible(
                                f"<code>{output}</code> {i + 1}/{len(sandbox_response.outputs)} {format_sandbox_success(sandbox_response.success)}",
                                f"<pre>{clean_logs(output)}</pre>",
                                i == len(sandbox_response.outputs) - 1,
                            )
                            for i, output in enumerate(sandbox_response.outputs)
                            if len(sandbox_response.outputs) > 0
                        ]
                    )
                ),
                opened=True,
            )
        )
        if sandbox_response
        else ""
    )

    updated_contents = updated_contents.replace("```", "\`\`\`")
    diff = generate_diff(file_contents, updated_contents).replace("```", "\`\`\`")
    diff_display = (
        f"Updated Code:\n\n```{ext}\n{updated_contents}```\nDiff:\n```diff\n{diff}\n```"
        if diff
        else f"Sandbox made no changes to {file_name} (formatters were not configured or Sweep didn't make changes)."
    )

    edit_sweep_comment(
        f"{logs}\n{diff_display}",
        2,
    )
    edit_sweep_comment("N/A", 3)
    logger.info("Sandbox comments updated")


def review_code(
    repo,
    pr_changes,
    issue_url,
    username,
    repo_description,
    title,
    summary,
    replies_text,
    tree,
    lint_output,
    plan,
    chat_logger,
    review_message,
    edit_sweep_comment,
    repo_full_name,
    installation_id,
):
    try:
        # CODE REVIEW
        changes_required = False
        changes_required, review_comment = review_pr(
            repo=repo,
            pr=pr_changes,
            issue_url=issue_url,
            username=username,
            repo_description=repo_description,
            title=title,
            summary=summary,
            replies_text=replies_text,
            tree=tree,
            lint_output=lint_output,
            plan=plan,  # plan for the PR
            chat_logger=chat_logger,
        )
        lint_output = None
        review_message += (
            f"Here is the {ordinal(1)} review\n" + blockquote(review_comment) + "\n\n"
        )
        if changes_required:
            edit_sweep_comment(
                review_message + "\n\nI'm currently addressing these suggestions.",
                3,
            )
            logger.info(f"Addressing review comment {review_comment}")
            on_comment(
                repo_full_name=repo_full_name,
                repo_description=repo_description,
                comment=review_comment,
                username=username,
                installation_id=installation_id,
                pr_path=None,
                pr_line_position=None,
                pr_number=None,
                pr=pr_changes,
                chat_logger=chat_logger,
                repo=repo,
            )
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
    return changes_required, review_message


def get_branch_diff_text(repo, branch, base_branch=None):
    base_branch = base_branch or SweepConfig.get_branch(repo)
    comparison = repo.compare(base_branch, branch)
    file_diffs = comparison.files

    pr_diffs = []
    for file in file_diffs:
        diff = file.patch
        if (
            file.status == "added"
            or file.status == "modified"
            or file.status == "removed"
        ):
            pr_diffs.append((file.filename, diff))
        else:
            logger.info(
                f"File status {file.status} not recognized"
            )  # TODO(sweep): We don't handle renamed files
    return "\n".join([f"{filename}\n{diff}" for filename, diff in pr_diffs])


def get_payment_messages(chat_logger: ChatLogger):
    if chat_logger:
        is_paying_user = chat_logger.is_paying_user()
        is_consumer_tier = chat_logger.is_consumer_tier()
        use_faster_model = OPENAI_USE_3_5_MODEL_ONLY or chat_logger.use_faster_model()
    else:
        is_paying_user = True
        is_consumer_tier = False
        use_faster_model = False

    tracking_id = chat_logger.data["tracking_id"] if chat_logger else None

    # Find the first comment made by the bot
    tickets_allocated = 5
    if is_consumer_tier:
        tickets_allocated = 15
    if is_paying_user:
        tickets_allocated = 500
    purchased_ticket_count = (
        chat_logger.get_ticket_count(purchased=True) if chat_logger else 0
    )
    ticket_count = (
        max(tickets_allocated - chat_logger.get_ticket_count(), 0)
        + purchased_ticket_count
        if chat_logger
        else 999
    )
    daily_ticket_count = (
        (3 - chat_logger.get_ticket_count(use_date=True) if not use_faster_model else 0)
        if chat_logger
        else 999
    )

    model_name = "GPT-3.5" if use_faster_model else "GPT-4"
    payment_link = "https://sweep.dev/pricing"
    single_payment_link = "https://buy.stripe.com/00g3fh7qF85q0AE14d"
    pro_payment_link = "https://buy.stripe.com/00g5npeT71H2gzCfZ8"
    daily_message = (
        f" and {daily_ticket_count} for the day"
        if not is_paying_user and not is_consumer_tier
        else ""
    )
    user_type = "💎 <b>Sweep Pro</b>" if is_paying_user else "⚡ <b>Sweep Basic Tier</b>"
    gpt_tickets_left_message = (
        f"{ticket_count} GPT-4 tickets left for the month"
        if not is_paying_user
        else "unlimited GPT-4 tickets"
    )
    purchase_message = f"<br/><br/> For more GPT-4 tickets, visit <a href={single_payment_link}>our payment portal</a>. For a one week free trial, try <a href={pro_payment_link}>Sweep Pro</a> (unlimited GPT-4 tickets)."
    payment_message = (
        f"{user_type}: I used {model_name} to create this ticket. You have {gpt_tickets_left_message}{daily_message}. (tracking ID: <code>{tracking_id}</code>)"
        + (purchase_message if not is_paying_user else "")
    )
    payment_message_start = (
        f"{user_type}: I'm using {model_name}. You have {gpt_tickets_left_message}{daily_message}. (tracking ID: <code>{tracking_id}</code>)"
        + (purchase_message if not is_paying_user else "")
    )

    return payment_message, payment_message_start
