from sweepai.utils.search_and_replace import score_multiline

haystack = r"""
# TODO: Add file validation

import math
import re
import traceback
import openai

import github
from github import GithubException, BadCredentialsException
from tabulate import tabulate
from tqdm import tqdm

from sweepai.logn import logger, LogTask
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



def center(text: str) -> str:
    return f"<div align='center'>{text}</div>"


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
    summary = re.sub(
        "---\s+Checklist:\n\n- \[[ X]\].*", "", summary, flags=re.DOTALL
    ).strip()

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
        actions_message = create_action_buttons(
            [
                "↻ Restart Sweep",
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
            pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Errored&width=600' alt='{index}%' />"
            return (
                f"{center(sweeping_gif)}<br/>{center(pbar)}\n\n"
                + f"\n\n---\n{actions_message}"
            )
        pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Progress&width=600' alt='{index}%' />"
        return (
            f"{center(sweeping_gif)}<br/>{center(pbar)}"
            + ("\n" + stars_suffix if index != -1 else "")
            + "\n"
            + payment_message_start
            + config_pr_message
            + f"\n\n---\n{actions_message}"
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
                f" contact team@sweep.dev.\n\n> @{username}, editing this issue description to include more details will automatically make me relaunch."
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
        cloned_repo=cloned_repo,
    )

    # Check repository for sweep.yaml/sweep.yml file.
    sweep_yml_exists = False
    for content_file in repo.get_contents(""):
        if content_file.name == "sweep.yaml" or content_file.name == "sweep.yml":
            sweep_yml_exists = True
            break

    # If sweep.yaml does not exist, then create a new PR that simply creates the sweep.yaml file.
    if not sweep_yml_exists:
"""

needle = r"""
def get_comment_header(index, errored=False, pr_message="", done=False):
    ...
    return (
        f"{center(sweeping_gif)}<br/>{center(pbar)}"
        + ("\n" + stars_suffix if index != -1 else "")
        + "\n"
        + payment_message_start
        + config_pr_message
        + f"\n\n---\n{actions_message}"
    )
""".strip(
    "\n"
)

matched_section = r"""
    def get_comment_header(index, errored=False, pr_message="", done=False):
        config_pr_message = (
            "\n" + f"* Install Sweep Configs: [Pull Request]({config_pr_url})"
            if config_pr_url is not None
            else ""
        )
        actions_message = create_action_buttons(
            [
                "↻ Restart Sweep",
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
            pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Errored&width=600' alt='{index}%' />"
            return (
                f"{center(sweeping_gif)}<br/>{center(pbar)}\n\n"
                + f"\n\n---\n{actions_message}"
            )
        pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Progress&width=600' alt='{index}%' />"
        return (
            f"{center(sweeping_gif)}<br/>{center(pbar)}"
            + ("\n" + stars_suffix if index != -1 else "")
            + "\n"
            + payment_message_start
            + config_pr_message
            + f"\n\n---\n{actions_message}"
        )
""".strip(
    "\n"
)

score = score_multiline(needle.splitlines(), matched_section.splitlines())
print(score)

# best_match = find_best_match(needle, haystack)
# print("\n".join(haystack.splitlines()[best_match.start : best_match.end]))
