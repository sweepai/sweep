'''
On Github ticket, get ChatGPT to deal with it
'''

# TODO: Add file validation

import traceback

import modal
import openai
from loguru import logger
from tabulate import tabulate

from sweepai.core.entities import Snippet, NoFilesException
from sweepai.core.sweep_bot import SweepBot, MaxTokensExceeded
from sweepai.core.prompts import issue_comment_prompt
from sweepai.handlers.create_pr import create_pr, create_config_pr, safe_delete_sweep_branch
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.config.server import PREFIX, DB_MODAL_INST_NAME, UTILS_MODAL_INST_NAME, OPENAI_API_KEY, \
    GITHUB_BOT_TOKEN, \
    GITHUB_BOT_USERNAME
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client, search_snippets
from sweepai.utils.prompt_constructor import HumanMessagePrompt

github_access_token = GITHUB_BOT_TOKEN
openai.api_key = OPENAI_API_KEY

update_index = modal.Function.lookup(DB_MODAL_INST_NAME, "update_index")

sep = "\n---\n"
bot_suffix_starring = "⭐ If you are enjoying Sweep, please [star our repo](https://github.com/sweepai/sweep) so more people can hear about us!"
bot_suffix = f"\n{sep}I'm a bot that handles simple bugs and feature requests but I might make mistakes. Please be kind!"
discord_suffix = f'\n<sup>[Join Our Discord](https://discord.com/invite/sweep-ai)'

stars_suffix = "⭐ In the meantime, consider [starring our repo](https://github.com/sweepai/sweep) so more people can hear about us!"

collapsible_template = '''
<details>
  <summary>{summary}</summary>

  {body}
</details>
'''

chunker = modal.Function.lookup(UTILS_MODAL_INST_NAME, "Chunking.chunk")

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2
num_extended_snippets = 2


def post_process_snippets(snippets: list[Snippet], max_num_of_snippets: int = 5):
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


def on_ticket(
        title: str,
        summary: str,
        issue_number: int,
        issue_url: str,
        username: str,
        repo_full_name: str,
        repo_description: str,
        installation_id: int,
        comment_id: int = None
):
    # Check if the title starts with "sweep" or "sweep: " and remove it
    if title.lower().startswith("sweep: "):
        title = title[7:]
    elif title.lower().startswith("sweep "):
        title = title[6:]

    # Flow:
    # 1. Get relevant files
    # 2: Get human message
    # 3. Get files to change
    # 4. Get file changes
    # 5. Create PR

    organization, repo_name = repo_full_name.split("/")
    metadata = {
        "issue_url": issue_url,
        "repo_name": repo_name,
        "repo_description": repo_description,
        "username": username,
        "installation_id": installation_id,
        "function": "on_ticket",
        "mode": PREFIX,
    }
    posthog.capture(username, "started", properties=metadata)

    g = get_github_client(installation_id)

    logger.info(f"Getting repo {repo_full_name}")
    repo = g.get_repo(repo_full_name)
    current_issue = repo.get_issue(number=issue_number)
    if current_issue.state == 'closed':
        posthog.capture(username, "issue_closed", properties=metadata)
        return {"success": False, "reason": "Issue is closed"}
    item_to_react_to = current_issue.get_comment(comment_id) if comment_id else current_issue
    replies_text = ""
    comments = list(current_issue.get_comments())
    if comment_id:
        logger.info(f"Replying to comment {comment_id}...")
        replies_text = "\nComments:\n" + "\n".join(
            [
                issue_comment_prompt.format(
                    username=comment.user.login,
                    reply=comment.body,
                ) for comment in comments if comment.user.type == "User"
            ]
        )

    chat_logger = ChatLogger({
        'repo_name': repo_name,
        'title': title,
        'summary': summary + replies_text,
        "issue_number": issue_number,
        "issue_url": issue_url,
        "username": username,
        "repo_full_name": repo_full_name,
        "repo_description": repo_description,
        "installation_id": installation_id,
        "comment_id": comment_id,
    })

    # Check if branch was already created for this issue
    preexisting_branch = None
    prs = repo.get_pulls(state='open', sort='created', base=SweepConfig.get_branch(repo))
    for pr in prs:
        # Check if this issue is mentioned in the PR, and pr is owned by bot
        # This is done in create_pr, (pr_description = ...)
        if pr.user.login == GITHUB_BOT_USERNAME and f'Fixes #{issue_number}.\n' in pr.body:
            success = safe_delete_sweep_branch(pr, repo)

    # Add emojis
    eyes_reaction = item_to_react_to.create_reaction("eyes")
    # If SWEEP_BOT reacted to item_to_react_to with "rocket", then remove it.
    reactions = item_to_react_to.get_reactions()
    for reaction in reactions:
        if reaction.content == "rocket" and reaction.user.login == GITHUB_BOT_USERNAME:
            item_to_react_to.delete_reaction(reaction.id)

    # Creates progress bar ASCII for 0-5 states
    progress_headers = [
        None,
        "Step 1: 🔍 Code Search",
        "Step 2: 🧐 Snippet Analysis",
        "Step 3: 📝 Planning",
        "Step 4: ⌨️ Coding",
        "Step 5: 🔁 Code Review"
    ]

    config_pr_url = None

    def get_comment_header(index, errored=False, pr_message=""):
        config_pr_message = (
            "\n" + f"* Install Sweep Configs: [Pull Request]({config_pr_url})" if config_pr_url is not None else "")
        if index < 0: index = 0
        if index == 5:
            return pr_message + config_pr_message
        index *= 20
        index = min(100, index)
        if errored:
            return f"![{index}%](https://progress-bar.dev/{index}/?&title=Errored&width=600)"
        return f"![{index}%](https://progress-bar.dev/{index}/?&title=Progress&width=600)" + (
            "\n" + stars_suffix + config_pr_message if index != -1 else "")

    # Find the first comment made by the bot
    issue_comment = None
    is_paying_user = chat_logger.is_paying_user()
    tickets_allocated = 60 if is_paying_user else 3
    ticket_count = max(tickets_allocated - chat_logger.get_ticket_count(), 0)
    use_faster_model = chat_logger.use_faster_model()
    payment_message = f"To create this ticket, I used {'gpt-3.5. ' if use_faster_model else 'gpt-4. '}You have {ticket_count} gpt-4 tickets left." + (" For more gpt-4 tickets, visit [our payment portal.](https://buy.stripe.com/fZe03512h99u0AE6os)" if not is_paying_user else "")
    first_comment = f"{get_comment_header(0)}\n{sep}I am currently looking into this ticket!. I will update the progress of the ticket in this comment. I am currently searching through your code, looking for relevant snippets.\n{sep}## {progress_headers[1]}\nWorking on it...{bot_suffix}{discord_suffix}"
    for comment in comments:
        if comment.user.login == GITHUB_BOT_USERNAME:
            issue_comment = comment
            issue_comment.edit(first_comment)
            break
    if issue_comment is None:
        issue_comment = current_issue.create_comment(first_comment)

    # Comment edit function
    past_messages = {}
    current_index = {}

    def edit_sweep_comment(message: str, index: int, pr_message=""):
        nonlocal current_index
        # -1 = error, -2 = retry
        # Only update the progress bar if the issue generation errors.
        errored = (index == -1)
        if index >= 0:
            past_messages[index] = message
            current_index = index

        agg_message = None
        # Include progress history
        # index = -2 is reserved for
        for i in range(current_index + 2):  # go to next header (for Working on it... text)
            if i == 0 or i >= len(progress_headers): continue  # skip None header
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
            agg_message = "## ❌ Unable to Complete PR" + '\n' + message + "\nIf you would like to report this bug, please join our **[Discord](https://discord.com/invite/sweep-ai)**."
            suffix = bot_suffix # don't include discord suffix for error messages

        # Update the issue comment
        issue_comment.edit(f"{get_comment_header(current_index, errored, pr_message)}\n{sep}{agg_message}{suffix}")

    def log_error(error_type, exception):
        content = f"**{error_type} Error**\n{username}: {issue_url}\n```{exception}```"
        discord_log_error(content)

    def fetch_file_contents_with_retry():
        retries = 3
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

    logger.info("Fetching relevant files...")
    try:
        snippets, tree = fetch_file_contents_with_retry()
        assert len(snippets) > 0
    except Exception as e:
        trace = traceback.format_exc()
        logger.error(e)
        logger.error(trace)
        edit_sweep_comment(
            "It looks like an issue has occured around fetching the files. Perhaps the repo has not been initialized: try removing this repo and adding it back. I'll try again in a minute. If this error persists contact team@sweep.dev.",
            -1
        )
        log_error("File Fetch", str(e) + "\n" + traceback.format_exc())
        raise e

    snippets = post_process_snippets(snippets)

    snippets = post_process_snippets(snippets,
                                     max_num_of_snippets=2 if use_faster_model else 5)

    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary + replies_text,
        snippets=snippets,
        tree=tree,  # TODO: Anything in repo tree that has something going through is expanded
    )

    sweep_bot = SweepBot.from_system_message_content(
        human_message=human_message, repo=repo, is_reply=bool(comments), chat_logger=chat_logger
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
            logger.error("Failed to create new branch for sweep.yaml file.\n", e, traceback.format_exc())
    else:
        logger.info("sweep.yaml file already exists.")

    sweepbot_retries = 3
    try:
        for i in range(sweepbot_retries):
            # ANALYZE SNIPPETS
            if sweep_bot.model == "gpt-4-32k-0613":
                logger.info("CoT retrieval...")
                sweep_bot.cot_retrieval()
            else:
                logger.info("Did not execute CoT retrieval...")

            newline = '\n'
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
                ),
                1
            )

            # COMMENT ON ISSUE
            # TODO: removed issue commenting here
            logger.info("Fetching files to modify/create...")
            file_change_requests = sweep_bot.get_files_to_change()
            file_change_requests = sweep_bot.validate_file_change_requests(file_change_requests)
            table = tabulate(
                [[f"`{file_change_request.filename}`", file_change_request.instructions] for file_change_request in
                 file_change_requests],
                headers=["File Path", "Proposed Changes"],
                tablefmt="pipe"
            )
            edit_sweep_comment(
                "From looking through the relevant snippets, I decided to make the following modifications:\n\n" + table + "\n\n",
                2
            )

            # CREATE PR METADATA
            logger.info("Generating PR...")
            pull_request = sweep_bot.generate_pull_request()
            pull_request_content = pull_request.content.strip().replace("\n", "\n>")
            pull_request_summary = f"**{pull_request.title}**\n`{pull_request.branch_name}`\n>{pull_request_content}\n"
            edit_sweep_comment(
                f"I have created a plan for writing the pull request. I am now working my plan and coding the required changes to address this issue. Here is the planned pull request:\n\n{pull_request_summary}",
                3
            )

            # WRITE PULL REQUEST
            logger.info("Making PR...")
            response = create_pr(file_change_requests, pull_request, sweep_bot, username, installation_id, issue_number)
            if not response or not response["success"]: raise Exception("Failed to create PR")
            pr = response["pull_request"]
            current_issue.create_reaction("rocket")
            edit_sweep_comment(
                "I have finished coding the issue. I am now reviewing it for completeness.",
                4
            )

            try:
                current_issue.delete_reaction(eyes_reaction.id)
            except:
                pass
            try:
                # CODE REVIEW
                changes_required, review_comment = review_pr(repo=repo, pr=pr, issue_url=issue_url, username=username,
                                                             repo_description=repo_description, title=title,
                                                             summary=summary, replies_text=replies_text, tree=tree)
                logger.info(f"Addressing review comment {review_comment}")
                if changes_required:
                    on_comment(repo_full_name=repo_full_name,
                               repo_description=repo_description,
                               comment=review_comment,
                               username=username,
                               installation_id=installation_id,
                               pr_path=None,
                               pr_line_position=None,
                               pr_number=pr.number)
            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(e)

            # Completed code review
            edit_sweep_comment(
                "Success! 🚀",
                5,
                pr_message=f"## Here's the PR! [https://github.com/{repo_full_name}/pull/{pr.number}](https://github.com/{repo_full_name}/pull/{pr.number}).\n{payment_message}",
            )

            break
    except MaxTokensExceeded as e:
        logger.info("Max tokens exceeded")
        log_error("Max Tokens Exceeded", str(e) + "\n" + traceback.format_exc())
        if chat_logger.is_paying_user():
            edit_sweep_comment(f"Sorry, I could not edit `{e.filename}` as this file is too long. We are currently working on improved file streaming to address this issue.\n", -1)
        else:
            edit_sweep_comment(f"Sorry, I could not edit `{e.filename}` as this file is too long.\n\nIf this file is incorrect, please describe the desired file in the prompt. However, if you would like to edit longer files, consider upgrading to [Sweep Pro](https://sweep.dev/) for longer context lengths.\n", -1)
        raise e
    except NoFilesException:
        logger.info("No files to change.")
        log_error("No Files to Change", str(e) + "\n" + traceback.format_exc())
        edit_sweep_comment("Sorry, I could find any appropriate files to edit to address this issue. If this is a mistake, please provide more context and I will retry!", -1)
        raise e
    except openai.error.InvalidRequestError as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        edit_sweep_comment(
            "I'm sorry, but it looks our model has ran out of context length. We're trying to make this happen less, but one way to mitigate this is to code smaller files. If this error persists contact team@sweep.dev.",
            -1
        )
        log_error("Context Length", str(e) + "\n" + traceback.format_exc())
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
        edit_sweep_comment(
            "I'm sorry, but it looks like an error has occured. Try removing and re-adding the sweep label. If this error persists contact team@sweep.dev.",
            -1
        )
        log_error("Workflow", str(e) + "\n" + traceback.format_exc())
        posthog.capture(
            username,
            "failed",
            properties={"error": str(e), "reason": "Generic error", **metadata},
        )
        raise e
    else:
        try:
            item_to_react_to.delete_reaction(eyes_reaction.id)
        except:
            pass
        item_to_react_to.create_reaction("rocket")

    posthog.capture(username, "success", properties={**metadata})
    logger.info("on_ticket success")
    return {"success": True}
