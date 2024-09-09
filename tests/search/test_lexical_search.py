from sweepai.core.lexical_search import tokenize_call

file_contents = """\
# TODO: Add file validation

import math
import re
import traceback
import openai

import github
from github import GithubException, BadCredentialsException
from tabulate import tabulate
from tqdm import tqdm

from loguru import logger, LogTask
from sweepai.core.context_pruning import ContextPruning
from sweepai.core.documentation_searcher import extract_relevant_docs
from sweepai.core.entities import (
    ProposedIssue,
    SandboxResponse,
    Snippet,
    NoFilesException,
    SweepContext,
    MaxTokensExceeded,
    EmptyRepository,
)
from sweepai.core.external_searcher import ExternalSearcher
from sweepai.core.slow_mode_expand import SlowModeBot
from sweepai.core.sweep_bot import SweepBot
from sweepai.core.prompts import issue_comment_prompt

# from sandbox.sandbox_utils import Sandbox
from sweepai.handlers.create_pr import (
    create_pr_changes,
    create_config_pr,
    safe_delete_sweep_branch,
)
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from sweepai.utils.buttons import create_action_buttons
from sweepai.utils.chat_logger import ChatLogger
from sweepai.config.client import (
    SweepConfig,
    get_documentation_dict,
)
from sweepai.config.server import (
    ENV,
    MONGODB_URI,
    OPENAI_API_KEY,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_NAME,
    OPENAI_USE_3_5_MODEL_ONLY,
    WHITELISTED_REPOS,
)
from sweepai.utils.ticket_utils import *
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.search_utils import search_snippets
from sweepai.utils.tree_utils import DirectoryTree

openai.api_key = OPENAI_API_KEY


@LogTask()
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
):
    (
        title,
        slow_mode,
        do_map,
        subissues_mode,
        sandbox_mode,
        fast_mode,
        lint_mode,
    ) = strip_sweep(title)

    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR

    summary = summary or ""
    summary = re.sub(
        "<details (open)?>\n<summary>Checklist</summary>.*",
        "",
        summary,
        flags=re.DOTALL,
    ).strip()
    summary = re.sub("Checklist:\n\n- \[[ X]\].*", "", summary, flags=re.DOTALL).strip()

    repo_name = repo_full_name
    user_token, g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    current_issue = repo.get_issue(number=issue_number)
    assignee = current_issue.assignee.login if current_issue.assignee else None
    if assignee is None:
        assignee = current_issue.user.login

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
            }
        )
        if MONGODB_URI
        else None
    )

    if chat_logger:
        is_paying_user = chat_logger.is_paying_user()
        is_trial_user = chat_logger.is_trial_user()
        use_faster_model = OPENAI_USE_3_5_MODEL_ONLY or chat_logger.use_faster_model(g)
    else:
        is_paying_user = True
        is_trial_user = False
        use_faster_model = False

    if fast_mode:
        use_faster_model = True

    sweep_context = SweepContext.create(
        username=username,
        issue_url=issue_url,
        use_faster_model=use_faster_model,
        is_paying_user=is_paying_user,
        repo=repo,
        token=user_token,
    )
    logger.print(sweep_context)

    if not comment_id and not edited and chat_logger:
        chat_logger.add_successful_ticket(
            gpt3=use_faster_model
        )  # moving higher, will increment the issue regardless of whether it's a success or not

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
    }
    # logger.bind(**metadata)
    posthog.capture(username, "started", properties=metadata)

    logger.info(f"Getting repo {repo_full_name}")

    if current_issue.state == "closed":
        logger.warning(f"Issue {issue_number} is closed")
        posthog.capture(username, "issue_closed", properties=metadata)
        return {"success": False, "reason": "Issue is closed"}
    current_issue.edit(body=summary)
    item_to_react_to = (
        current_issue.get_comment(comment_id) if comment_id else current_issue
    )
    replies_text = ""
    comments = list(current_issue.get_comments())
    if comment_id:
        logger.info(f"Replying to comment {comment_id}...")
        replies_text = "\nComments:\n" + "\n".join(
            [
                issue_comment_prompt.format(
                    username=comment.user.login,
                    reply=comment.body,
                )
                for comment in comments
                if comment.user.type == "User"
            ]
        )
    summary = summary if summary else ""

    prs = repo.get_pulls(
        state="open", sort="created", base=SweepConfig.get_branch(repo)
    )
    for pr in prs:
        # Check if this issue is mentioned in the PR, and pr is owned by bot
        # This is done in create_pr, (pr_description = ...)
        if (
            pr.user.login == GITHUB_BOT_USERNAME
            and f"Fixes #{issue_number}.\n" in pr.body
        ):
            success = safe_delete_sweep_branch(pr, repo)

    eyes_reaction = item_to_react_to.create_reaction("eyes")
    # If SWEEP_BOT reacted to item_to_react_to with "rocket", then remove it.
    reactions = item_to_react_to.get_reactions()
    for reaction in reactions:
        if reaction.content == "rocket" and reaction.user.login == GITHUB_BOT_USERNAME:
            item_to_react_to.delete_reaction(reaction.id)

    # Removed 1, 3
    progress_headers = [
        None,
        "Step 1: 🔎 Searching",
        "Step 2: ⌨️ Coding",
        "Step 3: 🔁 Code Review",
    ]

    config_pr_url = None

    # Find the first comment made by the bot
    issue_comment = None
    tickets_allocated = 5
    if is_trial_user:
        tickets_allocated = 15
    if is_paying_user:
        tickets_allocated = 500
    ticket_count = (
        max(tickets_allocated - chat_logger.get_ticket_count(), 0)
        if chat_logger
        else 999
    )
    daily_ticket_count = (
        (3 - chat_logger.get_ticket_count(use_date=True) if not use_faster_model else 0)
        if chat_logger
        else 999
    )

    model_name = "GPT-3.5" if use_faster_model else "GPT-4"
    payment_link = "https://buy.stripe.com/00g5npeT71H2gzCfZ8"
    daily_message = (
        f" and {daily_ticket_count} for the day"
        if not is_paying_user and not is_trial_user
        else ""
    )
    user_type = "💎 Sweep Pro" if is_paying_user else "⚡ Sweep Free Trial"
    gpt_tickets_left_message = (
        f"{ticket_count} GPT-4 tickets left for the month"
        if not is_paying_user
        else "unlimited GPT-4 tickets"
    )
    payment_message = (
        f"{user_type}: I used {model_name} to create this ticket. You have {gpt_tickets_left_message}{daily_message}."
        + (
            f" For more GPT-4 tickets, visit [our payment portal.]({payment_link})"
            if not is_paying_user
            else ""
        )
    )
    payment_message_start = (
        f"{user_type}: I'm creating this ticket using {model_name}. You have {gpt_tickets_left_message}{daily_message}."
        + (
            f" For more GPT-4 tickets, visit [our payment portal.]({payment_link})"
            if not is_paying_user
            else ""
        )
    )

    def get_comment_header(index, errored=False, pr_message="", done=False):
        config_pr_message = (
            "\n" + f"* Install Sweep Configs: [Pull Request]({config_pr_url})"
            if config_pr_url is not None
            else ""
        )
        # Why is this so convoluted
        # config_pr_message = " To retrigger Sweep, edit the issue.\n" + config_pr_message
        actions_message = create_action_buttons(
            [
                "Restart Sweep",
            ]
        )

        if index < 0:
            index = 0
        if index == 4:
            return pr_message + f"\n\n---\n{actions_message}" + config_pr_message

        total = len(progress_headers)
        index += 1 if done else 0
        index *= 100 / total
        index = int(index)
        index = min(100, index)
        if errored:
            return (
                f"![{index}%](https://progress-bar.dev/{index}/?&title=Errored&width=600)"
                + f"\n\n---\n{actions_message}"
            )
        return (
            f"![{index}%](https://progress-bar.dev/{index}/?&title=Progress&width=600)"
            + ("\n" + stars_suffix if index != -1 else "")
            + "\n"
            + payment_message_start
            # + f"\n\n---\n{actions_message}"
            + config_pr_message
        )

    # Find Sweep's previous comment
    logger.print("USERNAME", GITHUB_BOT_USERNAME)
    for comment in comments:
        logger.print("COMMENT", comment.user.login)
        if comment.user.login == GITHUB_BOT_USERNAME:
            logger.print("Found comment")
            issue_comment = comment

    try:
        config = SweepConfig.get_config(repo)
    except EmptyRepository as e:
        logger.info("Empty repo")
        first_comment = (
            "Sweep is currently not supported on empty repositories. Please add some"
            f" code to your repository and try again.\n{sep}##"
            f" {progress_headers[1]}\n{bot_suffix}{discord_suffix}"
        )
        if issue_comment is None:
            issue_comment = current_issue.create_comment(first_comment)
        else:
            issue_comment.edit(first_comment)
        return {"success": False}

    cloned_repo = ClonedRepo(
        repo_full_name, installation_id=installation_id, token=user_token
    )
    num_of_files = cloned_repo.get_num_files_from_repo()
    time_estimate = math.ceil(3 + 5 * num_of_files / 1000)

    indexing_message = (
        "I'm searching for relevant snippets in your repository. If this is your first"
        " time using Sweep, I'm indexing your repository. This may take up to"
        f" {time_estimate} minutes. I'll let you know when I'm done."
    )
    first_comment = (
        f"{get_comment_header(0)}\n{sep}I am currently looking into this ticket! I"
        " will update the progress of the ticket in this comment. I am currently"
        f" searching through your code, looking for relevant snippets.\n{sep}##"
        f" {progress_headers[1]}\n{indexing_message}{bot_suffix}{discord_suffix}"
    )

    if issue_comment is None:
        issue_comment = current_issue.create_comment(first_comment)
    else:
        issue_comment.edit(first_comment)

    # Comment edit function
    past_messages = {}
    current_index = 0

    # Random variables to save in case of errors
    table = None  # Show plan so user can finetune prompt

    def edit_sweep_comment(message: str, index: int, pr_message="", done=False):
        nonlocal current_index, user_token, g, repo, issue_comment
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
                " **[Discord](https://discord.com/invite/sweep-ai)**."
            )
            if table is not None:
                agg_message = (
                    agg_message
                    + f"\n{sep}Please look at the generated plan. If something looks"
                    f" wrong, please add more details to your issue.\n\n{table}"
                )
            suffix = bot_suffix  # don't include discord suffix for error messages

        # Update the issue comment
        try:
            issue_comment.edit(
                f"{get_comment_header(current_index, errored, pr_message, done=done)}\n{sep}{agg_message}{suffix}"
            )
        except BadCredentialsException:
            logger.error("Bad credentials, refreshing token")
            _user_token, g = get_github_client(installation_id)
            repo = g.get_repo(repo_full_name)
            issue_comment = repo.get_issue(current_issue.number)
            issue_comment.edit(
                f"{get_comment_header(current_index, errored, pr_message, done=done)}\n{sep}{agg_message}{suffix}"
            )

    if len(title + summary) < 20:
        logger.info("Issue too short")
        edit_sweep_comment(
            (
                "Please add more details to your issue. I need at least 20 characters"
                " to generate a plan."
            ),
            -1,
        )
        return {"success": True}

    if (
        repo_name.lower() not in WHITELISTED_REPOS
        and not is_paying_user
        and not is_trial_user
    ):
        if ("sweep" in repo_name.lower()) or ("test" in repo_name.lower()):
            logger.info("Test repository detected")
            edit_sweep_comment(
                (
                    "Sweep does not work on test repositories. Please create an issue"
                    " on a real repository. If you think this is a mistake, please"
                    " report this at https://discord.gg/sweep."
                ),
                -1,
            )
            return {"success": False}

    if lint_mode:
        # Get files to change
        # Create new branch
        # Send request to endpoint
        for file_path in []:
            SweepBot.run_sandbox(
                repo.html_url, file_path, None, user_token, only_lint=True
            )

    logger.info("Fetching relevant files...")
    try:
        snippets, tree = search_snippets(
            cloned_repo,
            f"{title}\n{summary}\n{replies_text}",
            num_files=num_of_snippets_to_query,
        )
        assert len(snippets) > 0
    except SystemExit:
        raise SystemExit
    except Exception as e:
        trace = traceback.format_exc()
        logger.error(e)
        logger.error(trace)
        edit_sweep_comment(
            (
                "It looks like an issue has occurred around fetching the files."
                " Perhaps the repo has not been initialized. If this error persists"
                f" contact team@sweep.dev.\n\n> @{username}, please edit the issue"
                " description to include more details and I will automatically"
                " relaunch."
            ),
            -1,
        )
        log_error(
            is_paying_user,
            is_trial_user,
            username,
            issue_url,
            "File Fetch",
            str(e) + "\n" + traceback.format_exc(),
            priority=1,
        )
        raise e

    snippets = post_process_snippets(
        snippets, max_num_of_snippets=2 if use_faster_model else 5
    )

    if not repo_description:
        repo_description = "No description provided."

    message_summary = summary + replies_text
    external_results = ExternalSearcher.extract_summaries(message_summary)
    if external_results:
        message_summary += "\n\n" + external_results
    user_dict = get_documentation_dict(repo)
    docs_results = ""
    try:
        docs_results = extract_relevant_docs(
            title + message_summary, user_dict, chat_logger
        )
        if docs_results:
            message_summary += "\n\n" + docs_results
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(f"Failed to extract docs: {e}")

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

    context_pruning = ContextPruning(chat_logger=chat_logger)
    (
        snippets_to_ignore,
        excluded_dirs,
    ) = context_pruning.prune_context(  # TODO, ignore directories
        human_message, repo=repo
    )
    snippets = post_process_snippets(
        snippets, max_num_of_snippets=5, exclude_snippets=snippets_to_ignore
    )
    dir_obj = DirectoryTree()
    dir_obj.parse(tree)
    dir_obj.remove_multiple(excluded_dirs)
    tree = str(dir_obj)
    logger.info(f"New snippets: {snippets}")
    logger.info(f"New tree: {tree}")
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
        sweep_context=sweep_context,
    )

    # Check repository for sweep.yml file.
    sweep_yml_exists = False
    for content_file in repo.get_contents(""):
        if content_file.name == "sweep.yaml":
            sweep_yml_exists = True
            break

    # If sweep.yaml does not exist, then create a new PR that simply creates the sweep.yaml file.
    if not sweep_yml_exists:
        try:
            logger.info("Creating sweep.yaml file...")
            config_pr = create_config_pr(sweep_bot)
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
                "Some code snippets I looked at (click to expand). If some file is"
                " missing from here, you can mention the path in the ticket"
                " description.",
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
            return {"success": True}

        # COMMENT ON ISSUE
        # TODO: removed issue commenting here
        logger.info("Fetching files to modify/create...")
        file_change_requests, plan = sweep_bot.get_files_to_change()

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

        sweep_bot.summarize_snippets()

        file_change_requests = sweep_bot.validate_file_change_requests(
            file_change_requests
        )
        table = tabulate(
            [
                [
                    f"`{file_change_request.filename}`",
                    file_change_request.instructions_display.replace(
                        "\n", "<br/>"
                    ).replace("```", "\\```"),
                ]
                for file_change_request in file_change_requests
            ],
            headers=["File Path", "Proposed Changes"],
            tablefmt="pipe",
        )
        # edit_sweep_comment(
        #     "From looking through the relevant snippets, I decided to make the"
        #     " following modifications:\n\n" + table + "\n\n",
        #     2,
        # )

        # TODO(lukejagg): Generate PR after modifications are made
        # CREATE PR METADATA
        logger.info("Generating PR...")
        pull_request = sweep_bot.generate_pull_request()
        # pull_request_content = pull_request.content.strip().replace("\n", "\n>")
        # pull_request_summary = f"**{pull_request.title}**\n`{pull_request.branch_name}`\n>{pull_request_content}\n"
        # edit_sweep_comment(
        #     (
        #         "I have created a plan for writing the pull request. I am now working"
        #         " my plan and coding the required changes to address this issue. Here"
        #         f" is the planned pull request:\n\n{pull_request_summary}"
        #     ),
        #     3,
        # )

        logger.info("Making PR...")

        files_progress: list[tuple[str, str, str, str]] = [
            (
                file_change_request.filename,
                file_change_request.instructions_display,
                "⏳ In Progress",
                "",
            )
            for file_change_request in file_change_requests
        ]

        checkboxes_progress: list[tuple[str, str, str]] = [
            (file_change_request.filename, file_change_request.instructions, " ")
            for file_change_request in file_change_requests
        ]
        checkboxes_contents = "\n".join(
            [
                create_checkbox(f"`{filename}`", blockquote(instructions), check == "X")
                for filename, instructions, check in checkboxes_progress
            ]
        )
        checkboxes_collapsible = create_collapsible(
            "Checklist", checkboxes_contents, opened=True
        )
        issue = repo.get_issue(number=issue_number)
        issue.edit(body=summary + "\n\n" + checkboxes_collapsible)

        delete_branch = False
        generator = create_pr_changes(  # make this async later
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
        for item in generator:
            if isinstance(item, dict):
                response = item
                break
            file_change_request, changed_file, sandbox_response, commit = item
            sandbox_response: SandboxResponse | None = sandbox_response
            format_exit_code = (
                lambda exit_code: "✓" if exit_code == 0 else f"❌ (`{exit_code}`)"
            )
            logger.print(sandbox_response)
            error_logs = (
                (
                    create_collapsible(
                        "Sandbox Execution Logs",
                        blockquote(
                            "\n\n".join(
                                [
                                    create_collapsible(
                                        f"<code>{execution.command.format(file_path=file_change_request.filename)}</code> {i + 1}/{len(sandbox_response.executions)} {format_exit_code(execution.exit_code)}",
                                        f"<pre>{clean_logs(execution.output)}</pre>",
                                        i == len(sandbox_response.executions) - 1,
                                    )
                                    for i, execution in enumerate(
                                        sandbox_response.executions
                                    )
                                    if len(sandbox_response.executions) > 0
                                    # And error code check
                                ]
                            )
                        ),
                        opened=True,
                    )
                )
                if sandbox_response
                else ""
            )
            if changed_file:
                logger.print("Changed File!")
                commit_hash = (
                    commit.sha
                    if commit is not None
                    else repo.get_branch(pull_request.branch_name).commit.sha
                )
                commit_url = f"https://github.com/{repo_full_name}/commit/{commit_hash}"
                checkboxes_progress = [
                    (
                        (
                            f"`{filename}` ✅ Commit [`{commit_hash[:7]}`]({commit_url})",
                            blockquote(instructions) + error_logs,
                            "X",
                        )
                        if file_change_request.filename == filename
                        else (filename, instructions, progress)
                    )
                    for filename, instructions, progress in checkboxes_progress
                ]
            else:
                logger.print("Didn't change file!")
                checkboxes_progress = [
                    (
                        (
                            f"`{filename}` ❌ Failed",
                            blockquote(instructions) + error_logs,
                            "X",
                        )
                        if file_change_request.filename == filename
                        else (filename, instructions, progress)
                    )
                    for filename, instructions, progress in checkboxes_progress
                ]
            checkboxes_contents = "\n".join(
                [
                    checkbox_template.format(
                        check=check,
                        filename=filename,
                        instructions=instructions,
                    )
                    for filename, instructions, check in checkboxes_progress
                ]
            )
            checkboxes_collapsible = collapsible_template.format(
                summary="Checklist",
                body=checkboxes_contents,
                opened="open",
            )
            issue = repo.get_issue(number=issue_number)
            issue.edit(body=summary + "\n\n" + checkboxes_collapsible)

            logger.info(files_progress)
            logger.info(f"Edited {file_change_request.filename}")
            edit_sweep_comment(checkboxes_contents, 2)
        if not response.get("success"):
            raise Exception(f"Failed to create PR: {response.get('error')}")
        pr_changes = response["pull_request"]

        edit_sweep_comment(
            "I have finished coding the issue. I am now reviewing it for completeness.",
            3,
        )
        change_location = f" [`{pr_changes.pr_head}`](https://github.com/{repo_full_name}/commits/{pr_changes.pr_head}).\n\n"
        review_message = "Here are my self-reviews of my changes at" + change_location

        lint_output = None
        try:
            current_issue.delete_reaction(eyes_reaction.id)
        except SystemExit:
            raise SystemExit
        except:
            pass

        changes_required = False
        try:
            # Todo(lukejagg): Pass sandbox linter results to review_pr
            # CODE REVIEW

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
            # Todo(lukejagg): Execute sandbox after each iteration
            lint_output = None
            review_message += (
                f"Here is the {ordinal(1)} review\n"
                + blockquote(review_comment)
                + "\n\n"
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

        if changes_required:
            edit_sweep_comment(
                review_message + "\n\nI finished incorporating these changes.",
                3,
            )
        else:
            edit_sweep_comment(
                f"I have finished reviewing the code for completeness. I did not find errors for {change_location}.",
                3,
            )

        is_draft = config.get("draft", False)
        try:
            pr = repo.create_pull(
                title=pr_changes.title,
                body=pr_changes.body,
                head=pr_changes.pr_head,
                base=SweepConfig.get_branch(repo),
                draft=is_draft,
            )
        except GithubException as e:
            is_draft = False
            pr = repo.create_pull(
                title=pr_changes.title,
                body=pr_changes.body,
                head=pr_changes.pr_head,
                base=SweepConfig.get_branch(repo),
                draft=is_draft,
            )

        pr.add_to_labels(GITHUB_LABEL_NAME)
        current_issue.create_reaction("rocket")

        logger.info("Running github actions...")
        try:
            if is_draft:
                logger.info("Skipping github actions because PR is a draft")
            else:
                commit = pr.get_commits().reversed[0]
                check_runs = commit.get_check_runs()

                for check_run in check_runs:
                    check_run.rerequest()
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(e)

        # Completed code review
        edit_sweep_comment(
            review_message + "\n\nSuccess! 🚀",
            4,
            pr_message=(
                f"## Here's the PR! [{pr.html_url}]({pr.html_url}).\n{payment_message}"
            ),
            done=True,
        )

        logger.info("Add successful ticket to counter")
    except MaxTokensExceeded as e:
        logger.info("Max tokens exceeded")
        log_error(
            is_paying_user,
            is_trial_user,
            username,
            issue_url,
            "Max Tokens Exceeded",
            str(e) + "\n" + traceback.format_exc(),
            priority=2,
        )
        if chat_logger.is_paying_user():
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
        logger.info("Sweep could not find files to modify")
        log_error(
            is_paying_user,
            is_trial_user,
            username,
            issue_url,
            "Sweep could not find files to modify",
            str(e) + "\n" + traceback.format_exc(),
            priority=2,
        )
        edit_sweep_comment(
            (
                "Sorry, Sweep could not find any appropriate files to edit to address"
                " this issue. If this is a mistake, please provide more context and I"
                f" will retry!\n\n> @{username}, please edit the issue description to"
                " include more details about this issue."
            ),
            -1,
        )
        delete_branch = True
        raise e
    except openai.error.InvalidRequestError as e:
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
            is_trial_user,
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
                "reason": "Invalid request error / context length",
                **metadata,
            },
        )
        delete_branch = True
        raise e
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        # title and summary are defined elsewhere
        if len(title + summary) < 60:
            edit_sweep_comment(
                (
                    "I'm sorry, but it looks like an error has occurred due to"
                    " insufficient information. Be sure to create a more detailed issue"
                    " so I can better address it. If this error persists report it at"
                    " https://discord.gg/sweep."
                ),
                -1,
            )
        else:
            edit_sweep_comment(
                (
                    "I'm sorry, but it looks like an error has occurred. Try changing"
                    " the issue description to re-trigger Sweep. If this error persists"
                    " contact team@sweep.dev."
                ),
                -1,
            )
        log_error(
            is_paying_user,
            is_trial_user,
            username,
            issue_url,
            "Workflow",
            str(e) + "\n" + traceback.format_exc(),
            priority=1,
        )
        posthog.capture(
            username,
            "failed",
            properties={"error": str(e), "reason": "Generic error", **metadata},
        )
        raise e
    else:
        try:
            item_to_react_to.delete_reaction(eyes_reaction.id)
            item_to_react_to.create_reaction("rocket")
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
            logger.print("Deleted branch", pull_request.branch_name)

    posthog.capture(username, "success", properties={**metadata})
    logger.info("on_ticket success")
    return {"success": True}
"""

tokens = tokenize_call(file_contents)
symbols = list(set([token.text for token in tokens]))
print(symbols)
