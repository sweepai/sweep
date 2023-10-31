from sweepai.config.client import (
    SweepConfig,
    RESTART_SWEEP_BUTTON,
    create_action_buttons,
    center,
    sweeping_gif,
    stars_suffix,
    payment_message_start,
    markdown_badge
)
from sweepai.core.entities import Snippet
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.str_utils import total_number_of_snippet_tokens
def get_comment_header(index, config_pr_url, progress_headers, errored=False, pr_message="", done=False):
    config_pr_message = (
        "\n"
        + f"<div align='center'>Install Sweep Configs: <a href='{config_pr_url}'>Pull Request</a></div>"
        if config_pr_url is not None
        else ""
    )
    actions_message = create_action_buttons(
        [
            RESTART_SWEEP_BUTTON,
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
        + center(payment_message_start)
        + center(f"\n\n{markdown_badge}")
        + config_pr_message
        + f"\n\n---\n{actions_message}"
    )

custom_config = """
extends: relaxed

rules:
    line-length: disable
    indentation: disable
"""

SLOW_MODE = False
SLOW_MODE = True


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
            snippet.file_path.startswith(exclude_snippet)
            for exclude_snippet in exclude_snippets
        )
    ]

    snippets = snippets[: min(len(snippets), max_num_of_snippets * 10)]
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


def log_error(
    is_paying_user,
    is_trial_user,
    username,
    issue_url,
    error_type,
    exception,
    priority=0,
):
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

    content = (
        f"**{error_type} Error**{prefix}\n{username}:"
        f" {issue_url}\n```{exception}```"
    )
    discord_log_error(content, priority=priority)
