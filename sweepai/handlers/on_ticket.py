"""
On Github ticket, get ChatGPT to deal with it
"""

# TODO: Add file validation

import math
import re
import traceback
import modal
import openai
import asyncio

from github import GithubException
from loguru import logger
from tabulate import tabulate
from sweepai.core.context_pruning import ContextPruning
from sweepai.core.documentation_searcher import DocumentationSearcher

from sweepai.core.entities import Snippet, NoFilesException, SweepContext
from sweepai.core.external_searcher import ExternalSearcher
from sweepai.core.slow_mode_expand import SlowModeBot
from sweepai.core.sweep_bot import SweepBot, MaxTokensExceeded
from sweepai.core.prompts import issue_comment_prompt
from sweepai.core.sandbox import Sandbox
from sweepai.handlers.create_pr import (
    create_pr_changes,
    create_config_pr,
    safe_delete_sweep_branch,
)
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.config.client import (
    SweepConfig,
    get_documentation_dict,
)
from sweepai.config.server import (
    PREFIX,
    DB_MODAL_INST_NAME,
    UTILS_MODAL_INST_NAME,
    OPENAI_API_KEY,
    GITHUB_BOT_TOKEN,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_NAME,
)
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import (
    get_github_client,
    get_num_files_from_repo,
    search_snippets,
)
from sweepai.utils.prompt_constructor import HumanMessagePrompt

github_access_token = GITHUB_BOT_TOKEN
openai.api_key = OPENAI_API_KEY

update_index = modal.Function.lookup(DB_MODAL_INST_NAME, "update_index")

sep = "\n---\n"
bot_suffix_starring = "⭐ If you are enjoying Sweep, please [star our repo](https://github.com/sweepai/sweep) so more people can hear about us!"
bot_suffix = (
    f"\n{sep} To recreate the pull request edit the issue title or description."
)
discord_suffix = f"\n<sup>[Join Our Discord](https://discord.com/invite/sweep-ai)"

stars_suffix = "⭐ In the meantime, consider [starring our repo](https://github.com/sweepai/sweep) so more people can hear about us!"

collapsible_template = """
<details>
<summary>{summary}</summary>

{body}
</details>
"""

checkbox_template = "- [{check}] `{filename}`\n> {instructions}\n"

chunker = modal.Function.lookup(UTILS_MODAL_INST_NAME, "chunk")

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2

ordinal = lambda n: str(n) + (
    "th" if 4 <= n <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
)


def post_process_snippets(
    snippets: list[Snippet],
    max_num_of_snippets: int = 5,
    exclude_snippets: list[str] = [],
):
    snippets = [
        snippet
        for snippet in snippets
        if not any(
            snippet.file_path.endswith(ext) for ext in SweepConfig().exclude_exts
        )
    ]
    snippets = [
        snippet
        for snippet in snippets
        if not any(
            snippet.file_path == exclude_file for exclude_file in exclude_snippets
        )
    ]
    for snippet in snippets[:num_full_files]:
        snippet = snippet.expand()

    # snippet fusing
    i = 0
    while i < len(snippets):
        j = i + 1
        while j < len(snippets):
            if snippets[i] ^ snippets[j]:  # this checks for overlap
                snippets[i] = snippets[i] | snippets[j]  # merging
                snippets.pop(j)
            else:
                j += 1
        i += 1

    # truncating snippets based on character length
    result_snippets = []
    total_length = 0
    for snippet in snippets:
        total_length += len(snippet.get_snippet())
        if total_length > total_number_of_snippet_tokens * 5:
            break
        result_snippets.append(snippet)
    return result_snippets[:max_num_of_snippets]


def strip_sweep(text: str):
    return (
        re.sub(
            r"^[Ss]weep\s?(\([Ss]low\))?(\([Mm]igrate\))?(\([Ff]ast\))?\s?:", "", text
        ).lstrip(),
        re.search(r"^[Ss]weep\s?\([Ss]low\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Mm]igrate\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ff]ast\)", text) is not None,
    )


async def on_ticket(
    title: str,
    summary: str,
    issue_number: int,
    issue_url: str,
    username: str,
    repo_full_name: str,
    repo_description: str,
    installation_id: int,
    comment_id: int = None,
):
    (
        title,
        slow_mode,
        migrate,
        fast_mode,
    ) = strip_sweep(title)

    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR

    summary = summary or ""
    summary = re.sub(
        "<details>\n<summary>Checklist</summary>.*", "", summary, flags=re.DOTALL
    )
    summary = re.sub("Checklist:\n\n- \[[ X]\].*", "", summary, flags=re.DOTALL)

    repo_name = repo_full_name

    chat_logger = ChatLogger(
        {
            "repo_name": repo_name,
            "title": title,
            "summary": summary,
            "issue_number": issue_number,
            "issue_url": issue_url,
            "username": username,
            "repo_full_name": repo_full_name,
            "repo_description": repo_description,
            "installation_id": installation_id,
            "comment_id": comment_id,
        }
    )
    sweep_context = SweepContext(issue_url=issue_url)

    user_token, g = get_github_client(installation_id)

    is_paying_user = chat_logger.is_paying_user()
    is_trial_user = chat_logger.is_trial_user()
    use_faster_model = chat_logger.use_faster_model(g)

    chat_logger.add_successful_ticket(
        gpt3=use_faster_model
    )  # moving higher, will increment the issue regardless of whether it's a success or not

    if fast_mode:
        use_faster_model = True

    organization, repo_name = repo_full_name.split("/")
    metadata = {
        "issue_url": issue_url,
        "repo_name": repo_name,
        "repo_description": repo_description,
        "username": username,
        "installation_id": installation_id,
        "function": "on_ticket",
        "model": "gpt-3.5" if use_faster_model else "gpt-4",
        "tier": "pro" if is_paying_user else "free",
        "mode": PREFIX,
    }
    posthog.capture(username, "started", properties=metadata)

    logger.info(f"Getting repo {repo_full_name}")
    repo = g.get_repo(repo_full_name)
    config = SweepConfig.get_config(repo)

    current_issue = repo.get_issue(number=issue_number)
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

    progress_headers = [
        None,
        "Step 1: 🔍 Code Search",
        "Step 2: 🧐 Snippet Analysis",
        "Step 3: 📝 Planning",
        "Step 4: ⌨️ Coding",
        "Step 5: 🔁 Code Review",
    ]

    config_pr_url = None

    # Find the first comment made by the bot
    issue_comment = None
    tickets_allocated = 5
    if is_trial_user:
        tickets_allocated = 15
    if is_paying_user:
        tickets_allocated = 120
    ticket_count = max(tickets_allocated - chat_logger.get_ticket_count(), 0)
    daily_ticket_count = (
        2 - chat_logger.get_ticket_count(use_date=True) if not use_faster_model else 0
    )
    slow_mode = slow_mode and not use_faster_model

    model_name = "GPT-3.5" if use_faster_model else "GPT-4"
    payment_link = "https://buy.stripe.com/6oE5npbGVbhC97afZ4"
    daily_message = (
        f" and {daily_ticket_count} for the day"
        if not is_paying_user and not is_trial_user
        else ""
    )
    user_type = "💎 Sweep Pro" if is_paying_user else "⚡ Sweep Free Trial"
    payment_message = (
        f"{user_type}: I used {model_name} to create this ticket. You have {ticket_count} GPT-4 tickets left for the month{daily_message}."
        + (
            f" For more GPT-4 tickets, visit [our payment portal.]({payment_link})"
            if not is_paying_user
            else ""
        )
    )
    slow_mode_status = " using slow mode" if slow_mode else " "
    payment_message_start = (
        f"{user_type}: I'm creating this ticket using {model_name}{slow_mode_status}. You have {ticket_count} GPT-4 tickets left{daily_message}."
        + (
            f" For more GPT-4 tickets, visit [our payment portal.]({payment_link})"
            if not is_paying_user
            else ""
        )
    )

    def get_comment_header(index, errored=False, pr_message=""):
        config_pr_message = (
            "\n" + f"* Install Sweep Configs: [Pull Request]({config_pr_url})"
            if config_pr_url is not None
            else ""
        )
        config_pr_message = " To retrigger Sweep edit the issue.\n" + config_pr_message
        if index < 0:
            index = 0
        if index == 6:
            return pr_message + config_pr_message
        index *= 100 / len(progress_headers)
        index = int(index)
        index = min(100, index)
        if errored:
            return f"![{index}%](https://progress-bar.dev/{index}/?&title=Errored&width=600)"
        return (
            f"![{index}%](https://progress-bar.dev/{index}/?&title=Progress&width=600)"
            + ("\n" + stars_suffix if index != -1 else "")
            + "\n"
            + payment_message_start
            + config_pr_message
        )

    num_of_files = get_num_files_from_repo(repo, installation_id)
    time_estimate = math.ceil(5 + 5 * num_of_files / 1000)  # idk how accurate this is

    indexing_message = f"I'm searching for relevant snippets in your repository. If this is your first time using Sweep, I'm indexing your repository. This may take {time_estimate} minutes. I'll let you know when I'm done."
    first_comment = f"{get_comment_header(0)}\n{sep}I am currently looking into this ticket!. I will update the progress of the ticket in this comment. I am currently searching through your code, looking for relevant snippets.\n{sep}## {progress_headers[1]}\n{indexing_message}{bot_suffix}{discord_suffix}"
    for comment in comments:
        if comment.user.login == GITHUB_BOT_USERNAME:
            issue_comment = comment
            issue_comment.edit(first_comment)
            break
    if issue_comment is None:
        issue_comment = current_issue.create_comment(first_comment)

    # Comment edit function
    past_messages = {}
    current_index = 0

    # Random variables to save in case of errors
    table = None  # Show plan so user can finetune prompt

    def edit_sweep_comment(message: str, index: int, pr_message=""):
        nonlocal current_index
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
                + "\n\nFor bonus GPT-4 tickets, please report this bug on **[Discord](https://discord.com/invite/sweep-ai)**."
            )
            if table is not None:
                agg_message = (
                    agg_message
                    + f"\n{sep}Please look at the generated plan. If something looks wrong, please add more details to your issue.\n\n{table}"
                )
            suffix = bot_suffix  # don't include discord suffix for error messages

        # Update the issue comment
        issue_comment.edit(
            f"{get_comment_header(current_index, errored, pr_message)}\n{sep}{agg_message}{suffix}"
        )

    if len(title + summary) < 20:
        edit_sweep_comment(
            "Please add more details to your issue. I need at least 20 characters to generate a plan.",
            -1,
        )

    if (repo_name != "sweep" and "sweep" in repo_name.lower()) or (
        repo_name != "test-canary" and "test" in repo_name.lower()
    ):
        # Todo(kevinlu1248): Instead of blocking, use faster model.
        edit_sweep_comment(
            "Sweep does not work on test repositories. Please create an issue on a real repository. If you think this is a mistake, please report this at https://discord.gg/sweep.",
            -1,
        )
        return {"success": False}

    def log_error(error_type, exception, priority=0):
        nonlocal is_paying_user, is_trial_user
        if is_paying_user or is_trial_user:
            if priority == 1:
                priority = 0
            elif priority == 2:
                priority = 1

        prefix = ""
        if is_trial_user:
            prefix = " (TRIAL)"
        if is_paying_user:
            prefix = " (PRO)"

        content = f"**{error_type} Error**{prefix}\n{username}: {issue_url}\n```{exception}```"
        discord_log_error(content, priority=priority)

    def fetch_file_contents_with_retry():
        retries = 1
        error = None
        for i in range(retries):
            try:
                logger.info(f"Fetching relevant files for the {i}th time...")
                return search_snippets(
                    repo,
                    f"{title}\n{summary}\n{replies_text}",
                    num_files=num_of_snippets_to_query,
                    branch=None,
                    installation_id=installation_id,
                )
            except Exception as e:
                error = e
                continue
        posthog.capture(
            username, "fetching_failed", properties={"error": error, **metadata}
        )
        raise error

    # Clone repo and perform local tests (linters, formatters, GHA)
    sandbox = None
    try:
        pass
        # Todo(lukejagg): Enable this once we have formatter working
        # Todo(lukejagg): allow configuration of sandbox (Python3, Nodejs, etc) (done?)
        # Todo(lukejagg): Max time limit for sandbox
        # logger.info("Initializing sandbox...")
        # sandbox = Sandbox.from_token(username, user_token, repo)
        # await sandbox.start()
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)

    logger.info("Fetching relevant files...")
    try:
        snippets, tree = fetch_file_contents_with_retry()
        assert len(snippets) > 0
    except Exception as e:
        trace = traceback.format_exc()
        logger.error(e)
        logger.error(trace)
        edit_sweep_comment(
            f"It looks like an issue has occurred around fetching the files. Perhaps the repo has not been initialized. If this error persists contact team@sweep.dev.\n\n> @{username}, please edit the issue description to include more details and I will automatically relaunch.",
            -1,
        )
        log_error("File Fetch", str(e) + "\n" + traceback.format_exc(), priority=1)
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
    docs_results = DocumentationSearcher.extract_relevant_docs(
        title + message_summary, user_dict
    )
    if docs_results:
        message_summary += "\n\n" + docs_results

    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=message_summary,
        snippets=snippets,
        tree=tree,
    )
    additional_plan = None
    if slow_mode and not use_faster_model:
        slow_mode_bot = SlowModeBot()
        queries, additional_plan = slow_mode_bot.expand_plan(human_message)

        snippets, tree = search_snippets(
            repo,
            f"{title}\n{summary}\n{replies_text}",
            num_files=num_of_snippets_to_query,
            branch=None,
            installation_id=installation_id,
            multi_query=queries,
        )
        snippets = post_process_snippets(snippets, max_num_of_snippets=5)
        human_message = HumanMessagePrompt(
            repo_name=repo_name,
            issue_url=issue_url,
            username=username,
            repo_description=repo_description,
            title=title,
            summary=message_summary + additional_plan,
            snippets=snippets,
            tree=tree,
        )
    try:
        context_pruning = ContextPruning(chat_logger=chat_logger)
        snippets_to_ignore, directories_to_ignore = context_pruning.prune_context(
            human_message, repo=repo
        )
        snippets, tree = search_snippets(
            repo,
            f"{title}\n{summary}\n{replies_text}",
            num_files=num_of_snippets_to_query,
            branch=None,
            installation_id=installation_id,
            excluded_directories=directories_to_ignore,  # handles the tree
        )
        snippets = post_process_snippets(
            snippets, max_num_of_snippets=5, exclude_snippets=snippets_to_ignore
        )
        logger.info(f"New snippets: {snippets}")
        logger.info(f"New tree: {tree}")
        if slow_mode and not use_faster_model and additional_plan is not None:
            message_summary += additional_plan
        human_message = HumanMessagePrompt(
            repo_name=repo_name,
            issue_url=issue_url,
            username=username,
            repo_description=repo_description,
            title=title,
            summary=message_summary,
            snippets=snippets,
            tree=tree,
        )
    except Exception as e:
        logger.error(f"Failed to prune context: {e}")

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
        logger.info("Did not execute CoT retrieval...")

        newline = "\n"
        edit_sweep_comment(
            "I found the following snippets in your repository. I will now analyze these snippets and come up with a plan."
            + "\n\n"
            + collapsible_template.format(
                summary="Some code snippets I looked at (click to expand). If some file is missing from here, you can mention the path in the ticket description.",
                body="\n".join(
                    [
                        f"https://github.com/{organization}/{repo_name}/blob/{repo.get_commits()[0].sha}/{snippet.file_path}#L{max(snippet.start, 1)}-L{min(snippet.end, snippet.content.count(newline))}\n"
                        for snippet in snippets
                    ]
                ),
            )
            + (
                f"I also found the following external resources that might be helpful:\n\n{external_results}\n\n"
                if external_results
                else ""
            )
            + (f"\n\n{docs_results}\n\n" if docs_results else ""),
            1,
        )

        # COMMENT ON ISSUE
        # TODO: removed issue commenting here
        logger.info("Fetching files to modify/create...")
        file_change_requests, plan = sweep_bot.get_files_to_change()

        if not file_change_requests:
            if len(title + summary) < 60:
                edit_sweep_comment(
                    "Sorry, I could not find any files to modify, can you please provide more details? Please make sure that the title and summary of the issue are at least 60 characters.",
                    -1,
                )
            else:
                edit_sweep_comment(
                    "Sorry, I could not find any files to modify, can you please provide more details?",
                    -1,
                )
            raise Exception("No files to modify.")

        sweep_bot.summarize_snippets(plan)

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
        edit_sweep_comment(
            "From looking through the relevant snippets, I decided to make the following modifications:\n\n"
            + table
            + "\n\n",
            2,
        )

        # TODO(lukejagg): Generate PR after modifications are made
        # CREATE PR METADATA
        logger.info("Generating PR...")
        pull_request = sweep_bot.generate_pull_request()
        pull_request_content = pull_request.content.strip().replace("\n", "\n>")
        pull_request_summary = f"**{pull_request.title}**\n`{pull_request.branch_name}`\n>{pull_request_content}\n"
        edit_sweep_comment(
            f"I have created a plan for writing the pull request. I am now working my plan and coding the required changes to address this issue. Here is the planned pull request:\n\n{pull_request_summary}",
            3,
        )

        logger.info("Making PR...")

        files_progress = [
            (
                file_change_request.filename,
                file_change_request.instructions_display,
                "⏳",
            )
            for file_change_request in file_change_requests
        ]

        checkboxes_progress = [
            (file_change_request.filename, file_change_request.instructions, " ")
            for file_change_request in file_change_requests
        ]
        checkboxes_message = collapsible_template.format(
            summary="Checklist",
            body="\n".join(
                [
                    checkbox_template.format(
                        check=check,
                        filename=filename,
                        instructions=instructions.replace("\n", "\n> "),
                    )
                    for filename, instructions, check in checkboxes_progress
                ]
            ),
        )
        issue = repo.get_issue(number=issue_number)
        issue.edit(body=summary + "\n\n" + checkboxes_message)

        generator = create_pr_changes(
            file_change_requests,
            pull_request,
            sweep_bot,
            username,
            installation_id,
            issue_number,
            sandbox=sandbox,
            chat_logger=chat_logger,
        )
        table_message = tabulate(
            [
                (f"`{filename}`", instructions.replace("\n", "<br/>"), progress)
                for filename, instructions, progress in files_progress
            ],
            headers=["File", "Instructions", "Progress"],
            tablefmt="pipe",
        )
        logger.info(files_progress)
        edit_sweep_comment(table_message, 4)
        response = {"error": NoFilesException()}
        for item in generator:
            if isinstance(item, dict):
                response = item
                break
            file_change_request, changed_file = item
            if changed_file:
                commit_hash = repo.get_branch(pull_request.branch_name).commit.sha
                commit_url = f"https://github.com/{repo_full_name}/commit/{commit_hash}"
                files_progress = [
                    (
                        file,
                        instructions,
                        f"✅ Commit [`{commit_hash[:7]}`]({commit_url})",
                    )
                    if file_change_request.filename == file
                    else (file, instructions, progress)
                    for file, instructions, progress in files_progress
                ]

                checkboxes_progress = [
                    (file, instructions, "X")
                    if file_change_request.filename == file
                    else (file, instructions, progress)
                    for file, instructions, progress in checkboxes_progress
                ]
                checkboxes_message = collapsible_template.format(
                    summary="Checklist",
                    body="\n".join(
                        [
                            checkbox_template.format(
                                check=check,
                                filename=filename,
                                instructions=instructions.replace("\n", "\n> "),
                            )
                            for filename, instructions, check in checkboxes_progress
                        ]
                    ),
                )
                issue = repo.get_issue(number=issue_number)
                issue.edit(body=summary + "\n\n" + checkboxes_message)
            else:
                files_progress = [
                    (file, instructions, "❌")
                    if file_change_request.filename == file
                    else (file, instructions, progress)
                    for file, instructions, progress in files_progress
                ]
            logger.info(files_progress)
            logger.info(f"Edited {file_change_request.filename}")
            table_message = tabulate(
                [
                    (f"`{filename}`", instructions.replace("\n", "<br/>"), progress)
                    for filename, instructions, progress in files_progress
                ],
                headers=["File", "Instructions", "Progress"],
                tablefmt="pipe",
            )
            edit_sweep_comment(table_message, 4)
        if not response.get("success"):
            raise Exception(f"Failed to create PR: {response.get('error')}")
        pr_changes = response["pull_request"]

        edit_sweep_comment(
            table_message
            + "I have finished coding the issue. I am now reviewing it for completeness.",
            4,
        )

        review_message = f"Here are my self-reviews of my changes at [`{pr_changes.pr_head}`](https://github.com/{repo_full_name}/commits/{pr_changes.pr_head}).\n\n"

        lint_output = None
        try:
            current_issue.delete_reaction(eyes_reaction.id)
        except:
            pass

        # Clone repo and perform local tests (linters, formatters, GHA)
        try:
            lint_sandbox = Sandbox.from_token(username, user_token, repo)
            if lint_sandbox is None:
                raise Exception("Sandbox is disabled")

            files = [
                f.filename
                for f in file_change_requests
                if (f.filename.endswith(".js") or f.filename.endswith(".ts"))
                and (f.change_type == "create" or f.change_type == "modify")
                and f.new_content is not None
            ]
            lint_output = await lint_sandbox.formatter_workflow(
                branch=pull_request.branch_name, files=files
            )

            # Todo(lukejagg): Is this necessary?
            # # Set file content:
            # for f in file_change_requests:
            #     print("E2B DEBUG", f.filename, f.new_content)
            #     if f.new_content is not None:
            #         await lint_sandbox.session.filesystem.write(
            #             f"/home/user/repo/{f.filename}", f.new_content
            #         )
            #         print(f"Wrote {f.filename}")

        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(e)

        for i in range(1 if not slow_mode else 3):
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
                    chat_logger=chat_logger,
                )
                # Todo(lukejagg): Execute sandbox after each iteration
                lint_output = None
                review_message += (
                    f"Here is the {ordinal(i + 1)} review\n> "
                    + review_comment.replace("\n", "\n> ")
                    + "\n\n"
                )
                edit_sweep_comment(
                    review_message + "\n\nI'm currently addressing these suggestions.",
                    5,
                )
                logger.info(f"Addressing review comment {review_comment}")
                if changes_required:
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
                    )
                else:
                    break
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(e)
                break

        edit_sweep_comment(
            review_message + "\n\nI finished incorporating these changes.", 5
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

        # Get the branch (SweepConfig.get_branch(repo))'s sha
        sha = repo.get_branch(SweepConfig.get_branch(repo)).commit.sha

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
        except Exception as e:
            logger.error(e)

        # Close sandbox
        try:
            if sandbox is not None:
                await asyncio.wait_for(sandbox.close(), timeout=10)
        except Exception as e:
            logger.error(e)

        # Completed code review
        edit_sweep_comment(
            review_message + "\n\nSuccess! 🚀",
            6,
            pr_message=f"## Here's the PR! [{pr.html_url}]({pr.html_url}).\n{payment_message}",
        )

        logger.info("Add successful ticket to counter")
    except MaxTokensExceeded as e:
        logger.info("Max tokens exceeded")
        log_error(
            "Max Tokens Exceeded",
            str(e) + "\n" + traceback.format_exc(),
            priority=2,
        )
        if chat_logger.is_paying_user():
            edit_sweep_comment(
                f"Sorry, I could not edit `{e.filename}` as this file is too long. We are currently working on improved file streaming to address this issue.\n",
                -1,
            )
        else:
            edit_sweep_comment(
                f"Sorry, I could not edit `{e.filename}` as this file is too long.\n\nIf this file is incorrect, please describe the desired file in the prompt. However, if you would like to edit longer files, consider upgrading to [Sweep Pro](https://sweep.dev/) for longer context lengths.\n",
                -1,
            )
        raise e
    except NoFilesException as e:
        logger.info("Sweep could not find files to modify")
        log_error(
            "Sweep could not find files to modify",
            str(e) + "\n" + traceback.format_exc(),
            priority=2,
        )
        edit_sweep_comment(
            f"Sorry, Sweep could not find any appropriate files to edit to address this issue. If this is a mistake, please provide more context and I will retry!\n\n> @{username}, please edit the issue description to include more details about this issue.",
            -1,
        )
        raise e
    except openai.error.InvalidRequestError as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        edit_sweep_comment(
            "I'm sorry, but it looks our model has ran out of context length. We're trying to make this happen less, but one way to mitigate this is to code smaller files. If this error persists report it at https://discord.gg/sweep.",
            -1,
        )
        log_error(
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
        raise e
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        # title and summary are defined elsewhere
        if len(title + summary) < 60:
            edit_sweep_comment(
                "I'm sorry, but it looks like an error has occurred due to insufficient information. Be sure to create a more detailed issue so I can better address it. If this error persists report it at https://discord.gg/sweep.",
                -1,
            )
        else:
            edit_sweep_comment(
                "I'm sorry, but it looks like an error has occurred. Try changing the issue description to re-trigger Sweep. If this error persists contact team@sweep.dev.",
                -1,
            )
        log_error("Workflow", str(e) + "\n" + traceback.format_exc(), priority=0)
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
        except Exception as e:
            logger.error(e)

    posthog.capture(username, "success", properties={**metadata})
    logger.info("on_ticket success")
    return {"success": True}
