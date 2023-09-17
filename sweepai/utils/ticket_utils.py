import re
from sweepai.config.client import (
    UPDATES_MESSAGE,
    SweepConfig,
)
from sweepai.core.entities import Snippet
from sweepai.utils.chat_logger import discord_log_error

sep = "\n---\n"
bot_suffix_starring = (
    "⭐ If you are enjoying Sweep, please [star our"
    " repo](https://github.com/sweepai/sweep) so more people can hear about us!"
)
bot_suffix = (
    f"\n{sep}\n{UPDATES_MESSAGE}\n{sep} 💡 To recreate the pull request edit the issue"
    " title or description. To tweak the pull request, leave a comment on the pull request."
)
discord_suffix = f"\n<sup>[Join Our Discord](https://discord.com/invite/sweep)"

stars_suffix = (
    "⭐ In the meantime, consider [starring our repo](https://github.com/sweepai/sweep)"
    " so more people can hear about us!"
)

collapsible_template = """
<details {opened}>
<summary>{summary}</summary>

{body}
</details>
"""

checkbox_template = "- [{check}] {filename}\n{instructions}\n"

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2

ordinal = lambda n: str(n) + (
    "th" if 4 <= n <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
)

SLOW_MODE = False
SLOW_MODE = True


def clean_logs(logs: str):
    cleaned_logs = re.sub(r"\x1b\[.*?[@-~]", "", logs.replace("```", "\`\`\`"))
    cleaned_logs = re.sub('\n{2,}', '\n', cleaned_logs)
    cleaned_logs = cleaned_logs or "(nothing was outputted)"
    return cleaned_logs


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


def create_collapsible(summary: str, body: str, opened: bool = False):
    return collapsible_template.format(
        summary=summary, body=body, opened="open" if opened else ""
    )

def create_checkbox(title: str, body: str, checked: bool = False):
    return checkbox_template.format(
        check="X" if checked else " ", filename=title, instructions=body
    )
    return checkbox_template.format(
        check="X" if checked else " ", filename=title, instructions=body
    )


def get_comment_header(index, errored=False, pr_message="", done=False):
    config_pr_message = (
        "\n" + f"* Install Sweep Configs: [Pull Request]({config_pr_url})"
        if config_pr_url is not None
        else ""
    )
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
        + config_pr_message
    )

def strip_sweep(text: str):
    return (
        re.sub(
            r"^[Ss]weep\s?(\([Ss]low\))?(\([Mm]ap\))?(\([Ff]ast\))?\s?:", "", text
        ).lstrip(),
        re.search(r"^[Ss]weep\s?\([Ss]low\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Mm]ap\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ss]ubissues?\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ss]andbox?\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ff]ast\)", text) is not None,
        re.search(r"^[Ss]weep\s?\([Ll]int\)", text) is not None,
    )

def edit_sweep_comment(message: str, index: int, pr_message="", done=False):
    nonlocal current_index, user_token, g, repo, issue_comment
    errored = index == -1
    if index >= 0:
        past_messages[index] = message
        current_index = index

    agg_message = None
    for i in range(
        current_index + 2
    ):
        if i == 0 or i >= len(progress_headers):
            continue
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
        suffix = bot_suffix
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

def handle_generic_exception(e, title, summary, is_paying_user, is_trial_user, username, issue_url, metadata):
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