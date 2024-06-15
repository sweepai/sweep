"""
on_ticket is the main function that is called when a new issue is created.
It is only called by the webhook handler in sweepai/api.py.
"""

import difflib
import io
import os
import re
import zipfile

import markdown
import requests
from github import Repository, IncompletableObject
from github.PullRequest import PullRequest
from github.Issue import Issue
from loguru import logger
from tqdm import tqdm
import hashlib


from sweepai.agents.pr_description_bot import PRDescriptionBot
from sweepai.config.client import (
    RESTART_SWEEP_BUTTON,
    SweepConfig,
)
from sweepai.core.entities import (
    SandboxResponse,
)
from sweepai.dataclasses.codereview import CodeReview, CodeReviewIssue
from sweepai.handlers.create_pr import (
    safe_delete_sweep_branch,
)
from sweepai.handlers.on_check_suite import clean_gh_logs, remove_ansi_tags
from sweepai.utils.buttons import create_action_buttons
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.concurrency_utils import fire_and_forget_wrapper
from sweepai.utils.github_utils import (
    CURRENT_USERNAME,
    get_github_client,
    get_token,
)
from sweepai.utils.str_utils import (
    BOT_SUFFIX,
    blockquote,
    bot_suffix,
    clean_logs,
    create_collapsible,
    discord_suffix,
    format_sandbox_success,
    sep,
    stars_suffix,
)
from sweepai.utils.user_settings import UserSettings


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

FAILING_GITHUB_ACTION_PROMPT = """\
The following Github Actions failed on a previous attempt at fixing this issue.
Propose a fix to the failing github actions. You must edit the source code, not the github action itself.
{github_action_log}
"""

SWEEP_PR_REVIEW_HEADER = "# Sweep: PR Review"

def center(text: str) -> str:
    return f"<div align='center'>{text}</div>"

# Add :eyes: emoji to ticket
def add_emoji(issue: Issue, comment_id: int = None, reaction_content="eyes"):
    item_to_react_to = issue.get_comment(comment_id) if comment_id else issue
    item_to_react_to.create_reaction(reaction_content)


# Add :eyes: emoji to ticket
def add_emoji_to_pr(pr: PullRequest, comment_id: int = None, reaction_content="eyes"):
    item_to_react_to = pr.get_comment(comment_id) if comment_id else pr
    item_to_react_to.create_reaction(reaction_content)


# If SWEEP_BOT reacted to item_to_react_to with "rocket", then remove it.
def remove_emoji(issue: Issue, comment_id: int = None, content_to_delete="eyes"):
    item_to_react_to = issue.get_comment(comment_id) if comment_id else issue
    reactions = item_to_react_to.get_reactions()
    for reaction in reactions:
        if (
            reaction.content == content_to_delete
            and reaction.user.login == CURRENT_USERNAME
        ):
            item_to_react_to.delete_reaction(reaction.id)


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

# takes in a list of workflow runs and returns a list of messages containing the logs of the failing runs
def get_failing_gha_logs(runs, installation_id) -> str:
    token = get_token(installation_id)
    all_logs = ""
    for run in runs:
        # jobs_url
        jobs_url = run.jobs_url
        jobs_response = requests.get(
            jobs_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if jobs_response.status_code == 200:
            failed_jobs = []
            jobs = jobs_response.json()["jobs"]
            for job in jobs:
                if job["conclusion"] == "failure":
                    failed_jobs.append(job)

            failed_jobs_name_list = []
            for job in failed_jobs:
                # add failed steps
                for step in job["steps"]:
                    if step["conclusion"] == "failure":
                        parsed_name = step['name'].replace('/','')
                        failed_jobs_name_list.append(
                            f"{job['name']}/{step['number']}_{parsed_name}"
                        )
        else:
            logger.error(
                "Failed to get jobs for failing github actions, possible a credentials issue"
            )
            return all_logs
        # make sure jobs in valid
        if jobs_response.json()["total_count"] == 0:
            logger.warning(f"no jobs for this run: {run}, continuing...")
            continue

        # logs url
        logs_url = run.logs_url
        logs_response = requests.get(
            logs_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            allow_redirects=True,
        )
        # Check if the request was successful
        if logs_response.status_code == 200:
            zip_data = io.BytesIO(logs_response.content)
            zip_file = zipfile.ZipFile(zip_data, "r")
            zip_file_names = zip_file.namelist()
            for file in failed_jobs_name_list:
                if f"{file}.txt" in zip_file_names:
                    logs = zip_file.read(f"{file}.txt").decode("utf-8")
                    logs_prompt = clean_gh_logs(logs)
                    all_logs += logs_prompt + "\n"
        else:
            logger.error(
                "Failed to get logs for failing github actions, likely a credentials issue"
            )
    return remove_ansi_tags(all_logs)


def delete_old_prs(repo: Repository, issue_number: int):
    logger.info("Deleting old PRs...")
    prs = repo.get_pulls(
        state="open",
        sort="created",
        direction="desc",
        base=SweepConfig.get_branch(repo),
    )
    for pr in tqdm(prs.get_page(0)):
        # # Check if this issue is mentioned in the PR, and pr is owned by bot
        # # This is done in create_pr, (pr_description = ...)
        if pr.user.login == CURRENT_USERNAME and f"Fixes #{issue_number}.\n" in pr.body:
            safe_delete_sweep_branch(pr, repo)
            break


def get_comment_header(
    index: int,
    progress_headers: list[None | str],
    payment_message_start: str,
    errored: bool = False,
    pr_message: str = "",
    done: bool = False,
    config_pr_url: str | None = None,
):
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
        return pr_message + config_pr_message + f"\n\n{actions_message}"

    total = len(progress_headers)
    index += 1 if done else 0
    index *= 100 / total
    index = int(index)
    index = min(100, index)
    if errored:
        pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Errored&width=600' alt='{index}%' />"
        return (
            f"{center(sweeping_gif)}<br/>{center(pbar)}\n\n" + f"\n\n{actions_message}"
        )
    pbar = f"\n\n<img src='https://progress-bar.dev/{index}/?&title=Progress&width=600' alt='{index}%' />"
    return (
        f"{center(sweeping_gif)}"
        + f"<br/>{center(pbar)}"
        + ("\n" + stars_suffix if index != -1 else "")
        + "\n"
        + center(payment_message_start)
        + config_pr_message
        + f"\n\n{actions_message}"
    )


def process_summary(summary, issue_number, repo_full_name, installation_id):
    summary = summary or ""
    summary = re.sub(
        "<details (open)?>(\r)?\n<summary>Checklist</summary>.*",
        "",
        summary,
        flags=re.DOTALL,
    ).strip()
    summary = re.sub(
        "---\s+Checklist:(\r)?\n(\r)?\n- \[[ X]\].*",
        "",
        summary,
        flags=re.DOTALL,
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
    branch_match = re.search(r"(\s[B|b]ranch:) *(?P<branch_name>.+?)(\s|$)", summary)
    overrided_branch_name = None
    if branch_match and "branch_name" in branch_match.groupdict():
        overrided_branch_name = (
            branch_match.groupdict()["branch_name"].strip().strip("`\"'")
        )
        # TODO: this code might be finicky, might have missed edge cases
        if overrided_branch_name.startswith("https://github.com/"):
            overrided_branch_name = overrided_branch_name.split("?")[0].split("tree/")[
                -1
            ]
        SweepConfig.get_branch(repo, overrided_branch_name)
    return (
        summary,
        repo_name,
        user_token,
        g,
        repo,
        current_issue,
        assignee,
        overrided_branch_name,
    )


def raise_on_no_file_change_requests(
    title, summary, edit_sweep_comment, file_change_requests, renames_dict
):
    if not file_change_requests and not renames_dict:
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
        raise Exception(
            "Sorry, we failed to make the file changes. Please report this and we will fix it."
        )


def rewrite_pr_description(
    issue_number, repo, overrided_branch_name, pull_request, pr_changes
):
    # change the body here
    diff_text = get_branch_diff_text(
        repo=repo,
        branch=pull_request.branch_name,
        base_branch=overrided_branch_name,
    )
    new_description = PRDescriptionBot().describe_diffs(
        diff_text,
        pull_request.title,
    )  # TODO: update the title as well
    if new_description:
        pr_changes.body = (
            f"{new_description}\n\nFixes"
            f" #{issue_number}.\n\n---\n\n{INSTRUCTIONS_FOR_REVIEW}{BOT_SUFFIX}"
        )
    return pr_changes


def send_email_to_user(
    title,
    issue_number,
    username,
    repo_full_name,
    tracking_id,
    repo_name,
    g,
    file_change_requests,
    pr_changes,
    pr,
):
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
            files_changed.append(f"<code>{fcr.filename}</code> (+{added}/-{removed})")
    user_settings.send_email(
        subject=f"Sweep Pull Request Complete for {repo_name}#{issue_number} {title}",
        html=email_template.format(
            name=name,
            pr_url=pr.html_url,
            issue_number=issue_number,
            repo_full_name=repo_full_name,
            pr_number=pr.number,
            summary=markdown.markdown(pr_changes.body),
            files_changed="\n".join([f"<li>{item}</li>" for item in files_changed]),
            sweeping_gif=sweeping_gif,
        ),
    )


def handle_empty_repository(comment_id, current_issue, progress_headers, issue_comment):
    first_comment = (
        "Sweep is currently not supported on empty repositories. Please add some"
        f" code to your repository and try again.\n{sep}##"
        f" {progress_headers[1]}\n{bot_suffix}{discord_suffix}"
    )
    if issue_comment is None:
        issue_comment = current_issue.create_comment(first_comment + BOT_SUFFIX)
    else:
        issue_comment.edit(first_comment + BOT_SUFFIX)
    fire_and_forget_wrapper(add_emoji)(
        current_issue, comment_id, reaction_content="confused"
    )
    fire_and_forget_wrapper(remove_emoji)(content_to_delete="eyes")


def get_branch_diff_text(repo, branch, base_branch=None):
    base_branch = base_branch or SweepConfig.get_branch(repo)
    comparison = repo.compare(base_branch, branch)
    file_diffs = comparison.files

    priorities = {
        "added": 0,
        "renamed": 1,
        "modified": 2,
        "removed": 3,
    }

    file_diffs = sorted(file_diffs, key=lambda x: priorities.get(x.status, 4))

    pr_diffs = []
    for file in file_diffs:
        diff = file.patch
        if (
            file.status == "added"
            or file.status == "modified"
            or file.status == "removed"
            or file.status == "renamed"
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
        use_faster_model = chat_logger.use_faster_model()
    else:
        is_paying_user = True
        is_consumer_tier = False
        use_faster_model = False

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

    single_payment_link = "https://buy.stripe.com/00g3fh7qF85q0AE14d"
    pro_payment_link = "https://buy.stripe.com/00g5npeT71H2gzCfZ8"
    daily_message = (
        f" and {daily_ticket_count} for the day"
        if not is_paying_user and not is_consumer_tier
        else ""
    )
    user_type = (
        "💎 <b>Sweep Pro</b>" if is_paying_user else "⚡ <b>Sweep Basic Tier</b>"
    )
    gpt_tickets_left_message = (
        f"{ticket_count} Sweep issues left for the month"
        if not is_paying_user
        else "unlimited Sweep issues"
    )
    purchase_message = f"<br/><br/> For more Sweep issues, visit <a href={single_payment_link}>our payment portal</a>. For a one week free trial, try <a href={pro_payment_link}>Sweep Pro</a> (unlimited GPT-4 tickets)."
    payment_message = (
        f"{user_type}: You have {gpt_tickets_left_message}{daily_message}"
        + (purchase_message if not is_paying_user else "")
    )
    payment_message_start = (
        f"{user_type}: You have {gpt_tickets_left_message}{daily_message}"
        + (purchase_message if not is_paying_user else "")
    )

    return payment_message, payment_message_start


def parse_issues_from_code_review(issue_string: str):
    issue_regex = r"<issue>(?P<issue>.*?)<\/issue>"
    issue_matches = list(re.finditer(issue_regex, issue_string, re.DOTALL))
    potential_issues = set()
    for issue in issue_matches:
        issue_content = issue.group("issue")
        issue_params = ["issue_description", "file_name", "line_number"]
        issue_args = {}
        issue_failed = False
        for param in issue_params:
            regex = rf"<{param}>(?P<{param}>.*?)<\/{param}>"
            result = re.search(regex, issue_content, re.DOTALL)
            try:
                issue_args[param] = result.group(param).strip()
            except AttributeError:
                issue_failed = True
                break
        if not issue_failed:
            potential_issues.add(CodeReviewIssue(**issue_args))
    return list(potential_issues)


# converts the list of issues inside a code_review into markdown text to display in a github comment
def render_code_review_issues(
    username: str,
    pr: PullRequest,
    code_review: CodeReview,
    issue_type: str = "",
    sorted_issues: list[CodeReviewIssue] = [], # changes how issues are rendered
):
    files_to_blobs = {file.filename: file.blob_url for file in list(pr.get_files())}
    # generate the diff urls
    files_to_diffs = {}
    for file_name, _ in files_to_blobs.items():
        sha_256 = hashlib.sha256(file_name.encode("utf-8")).hexdigest()
        files_to_diffs[file_name] = f"{pr.html_url}/files#diff-{sha_256}"
    if sorted_issues:
        code_issues = sorted_issues
    else:
        code_issues = code_review.issues
    if issue_type == "potential":
        code_issues = code_review.potential_issues
    code_issues_string = ""
    for issue in code_issues:
        if issue.file_name in files_to_blobs:
            issue_blob_url = (
                f"{files_to_blobs[issue.file_name]}#L{issue.line_number}"
            )
            issue_diff_url = (
                f"{files_to_diffs[issue.file_name]}R{issue.line_number}"
            )
            if sorted_issues:
                code_issues_string += f"<li>In `{issue.file_name}`: {issue.issue_description}</li>\n\n{issue_blob_url}\n[View Diff]({issue_diff_url})"
            else:
                code_issues_string += f"<li>{issue.issue_description}</li>\n\n{issue_blob_url}\n[View Diff]({issue_diff_url})"
    return code_issues_string


def escape_html(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;")


# make sure code blocks are render properly in github comments markdown
def format_code_sections(text: str) -> str:
    backtick_count = text.count("`")
    if backtick_count % 2 != 0:
        # If there's an odd number of backticks, return the original text
        return text
    result = []
    last_index = 0
    inside_code = False
    while True:
        try:
            index = text.index("`", last_index)
            result.append(text[last_index:index])
            if inside_code:
                result.append("</code>")
            else:
                result.append("<code>")
            inside_code = not inside_code
            last_index = index + 1
        except ValueError:
            # No more backticks found
            break
    result.append(text[last_index:])
    formatted_text = "".join(result)
    # Escape HTML characters within <code> tags
    formatted_text = formatted_text.replace("<code>", "<code>").replace(
        "</code>", "</code>"
    )
    parts = formatted_text.split("<code>")
    for i in range(1, len(parts)):
        code_content, rest = parts[i].split("</code>", 1)
        parts[i] = escape_html(code_content) + "</code>" + rest

    return "<code>".join(parts)


def create_review_comments_for_code_issues(
    pr: PullRequest,
    code_issues: list[CodeReviewIssue]
):
    commit_sha = pr.head.sha
    commits = list(pr.get_commits())
    pr_commit = None
    for commit in commits:
        if commit.sha == commit_sha:
            pr_commit = commit
            break
    for issue in code_issues:
        comment_body = issue.issue_description
        comment_line = int(issue.line_number)
        comment_path = os.path.normpath(issue.file_name)
        pr.create_review_comment(
            body=comment_body, 
            commit=pr_commit, 
            path=comment_path, 
            line=comment_line
        )


# turns code_review_by_file into markdown string
def render_pr_review_by_file(
    username: str,
    pr: PullRequest,
    code_review_by_file: dict[str, CodeReview],
    formatted_comment_threads: dict[str, str],
    pull_request_summary: str = "",
    dropped_files: list[str] = [],
    unsuitable_files: list[tuple[str, Exception]] = [],
    pr_authors: str = "",
) -> str:
    body = f"{SWEEP_PR_REVIEW_HEADER}\n"
    pr_summary = ""
    if pr_authors:
        body += f"Authors: {pr_authors}\n" if ", " in pr_authors else f"Author: {pr_authors}\n" 
    # pull request summary goes to the bottom
    if pull_request_summary:
        pr_summary += f"\n<h3>Summary</h3>\n{pull_request_summary}\n<hr>\n"
    issues_section = ""
    potential_issues_section = ""
    # build issues section
        # create review comments for all the issues
    all_issues = []
    all_potential_issues = []
    for _, code_review in code_review_by_file.items():
        all_issues.extend(code_review.issues)
        all_potential_issues.extend(code_review.potential_issues)
    create_review_comments_for_code_issues(pr, all_issues)
    # build potential issues section
    for file_name, code_review in code_review_by_file.items():
        potential_issues = code_review.potential_issues
        if potential_issues:
            potential_issues_string = render_code_review_issues(
                username, pr, code_review, issue_type="potential"
            )
            potential_issues_section += f"""<details>
<summary>{file_name}</summary>
<ul>{format_code_sections(potential_issues_string)}</ul></details>"""
    # add titles/dropdowns for issues and potential issues section depending on if there were any issues/potential issues
    if potential_issues_section:
        potential_issues_section = f"<details><summary><h3>Potential Issues</h3></summary><p><strong>Sweep is unsure if these are issues, but they might be worth checking out.</strong></p>\n\n{potential_issues_section}</details><hr>"
    # add footer describing dropped files
    footer = ""
    if len(dropped_files) == 1:
        footer += f"<p>{dropped_files[0]} was not reviewed because our filter identified it as typically a non-human-readable (auto-generated) or less important file (e.g., dist files, package.json, images). If this is an error, please let us know.</p>"
    elif len(dropped_files) > 1:
        dropped_files_string = "".join([f"<li>{file}</li>" for file in dropped_files])
        footer += f"<p>The following files were not reviewed because our filter identified them as typically non-human-readable (auto-generated) or less important files (e.g., dist files, package.json, images). If this is an error, please let us know.</p><ul>{dropped_files_string}</ul>"
    if len(unsuitable_files) == 1:
        footer += f"<p>The following file {unsuitable_files[0][0]} were not reviewed as they were deemed unsuitable for the following reason: {str(unsuitable_files[0][1])}. If this is an error please let us know.</p>"
    elif len(unsuitable_files) > 1:
        unsuitable_files_string = "".join(
            [
                f"<li>{file}: {str(exception)}</li>"
                for file, exception in unsuitable_files
            ]
        )
        footer += f"<p>The following files were not reviewed as they were deemed unsuitable for a variety of reasons. If this is an error please let us know.</p><ul>{unsuitable_files_string}</ul>"
    if len(all_issues) == 0 and len(all_potential_issues) == 0:
        issues_section = "The Pull Request looks good! Sweep did not find any issues."
        if not formatted_comment_threads:
            issues_section = "The Pull Request looks good! Sweep did not find any new issues."
    elif len(all_issues) == 0:
        issues_section = "The Pull Request looks good! Sweep did not find any issues but found some potential issues that you may want to take a look at."
        if not formatted_comment_threads:
            issues_section = "The Pull Request looks good! Sweep did not find any new issues but found some potential issues that you may want to take a look at."
    else:
        if len(all_issues) == 1:
            issues_section = f"\n\nSweep found `{len(all_issues)}` new issue.\n\n" 
        else:
            issues_section = f"\n\nSweep found `{len(all_issues)}` new issues.\n\n"
        issues_section += "Sweep has left comments on the pull request for you to review. \nYou may respond to any comment Sweep made your feedback will be taken into consideration if you run the review again. If Sweep made a mistake, you can resolve the comment or let Sweep know by responding to the comment."
    return body + issues_section + potential_issues_section + pr_summary + footer


# handles the creation or update of the Sweep comment letting the user know that Sweep is reviewing a pr
# returns the comment_id
def create_update_review_pr_comment(
    username: str,
    pr: PullRequest,
    formatted_comment_threads: dict[str, str],
    code_review_by_file: dict[str, CodeReview] | None = None,
    pull_request_summary: str = "",
    dropped_files: list[str] = [],
    unsuitable_files: list[tuple[str, Exception]] = [],
    error_message: str = "",  # passing in an error message takes priority over everything else
) -> int:
    comment_id = -1
    sweep_comment = None
    # comments that appear in the github ui in the conversation tab are considered issue comments
    pr_comments = list(pr.get_issue_comments())
    # make sure we don't already have a comment created
    for comment in pr_comments:
        # a comment has already been created
        if comment.body.startswith(SWEEP_PR_REVIEW_HEADER):
            comment_id = comment.id
            sweep_comment = comment
            break
    commits = list(pr.get_commits())
    pr_authors = set()
    try:
        pr_authors.add(f"{pr.user.login}")
    except Exception as e:
        logger.error(f"Failed to retrieve {pr.user}: {str(e)}")
    for commit in commits:
        author = commit.author
        try:
            if author:
                pr_authors.add(f"{author.login}")
        except IncompletableObject as e:
            logger.error(f"Failed to retrieve author {author} for commit {commit.sha}: {str(e)}")
    pr_authors = ", ".join(pr_authors)

    # comment has not yet been created
    if not sweep_comment:
        comment_content = (
            f"{SWEEP_PR_REVIEW_HEADER}\nSweep is currently reviewing your pr..."
        )
        if pr_authors:
            comment_content = f"{SWEEP_PR_REVIEW_HEADER}\nAuthors of pull request: {pr_authors}\n\nSweep is currently reviewing your pr..."
        sweep_comment = pr.create_issue_comment(comment_content)

    # update the comment
    if error_message:
        sweep_comment.edit(
            f"{SWEEP_PR_REVIEW_HEADER}\nSweep was unable to review your pull request due to the following reasons:\n\n{error_message}"
        )
        comment_id = sweep_comment.id
        return comment_id  # early return

    # update body of sweep_comment
    if code_review_by_file:
        rendered_pr_review = render_pr_review_by_file(
            username,
            pr,
            code_review_by_file,
            formatted_comment_threads,
            pull_request_summary=pull_request_summary,
            dropped_files=dropped_files,
            unsuitable_files=unsuitable_files,
            pr_authors=pr_authors,
        )
        sweep_comment.edit(rendered_pr_review)
    comment_id = sweep_comment.id
    return comment_id

