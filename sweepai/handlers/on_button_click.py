from github.Repository import Repository
from loguru import logger

from sweepai.config.client import (
    RESET_FILE,
    REVERT_CHANGED_FILES_TITLE,
    RULES_LABEL,
    RULES_TITLE,
    get_blocked_dirs,
)
from sweepai.config.server import MONGODB_URI
from sweepai.core.post_merge import PostMerge
from sweepai.events import IssueCommentRequest
from sweepai.handlers.on_merge import comparison_to_diff
from sweepai.handlers.pr_utils import make_pr
from sweepai.utils.buttons import ButtonList, check_button_title_match
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client


def handle_button_click(request_dict):
    request = IssueCommentRequest(**request_dict)
    user_token, gh_client = get_github_client(request_dict["installation"]["id"])
    button_list = ButtonList.deserialize(request_dict["comment"]["body"])
    selected_buttons = [button.label for button in button_list.get_clicked_buttons()]
    repo = gh_client.get_repo(
        request_dict["repository"]["full_name"]
    )  # do this after checking ref
    comment_id = request.comment.id
    pr = repo.get_pull(request_dict["issue"]["number"])
    comment = pr.get_issue_comment(comment_id)
    if check_button_title_match(
        REVERT_CHANGED_FILES_TITLE, request.comment.body, request.changes
    ):
        revert_files = []
        for button_text in selected_buttons:
            revert_files.append(button_text.split(f"{RESET_FILE} ")[-1].strip())
        handle_revert(revert_files, request_dict["issue"]["number"], repo)
        comment.edit(
            body=ButtonList(
                buttons=[
                    button
                    for button in button_list.buttons
                    if button.label not in selected_buttons
                ],
                title=REVERT_CHANGED_FILES_TITLE,
            ).serialize()
        )

    if check_button_title_match(RULES_TITLE, request.comment.body, request.changes):
        rules = []
        for button_text in selected_buttons:
            rules.append(button_text.split(f"{RULES_LABEL} ")[-1].strip())
        handle_rules(request_dict, rules, user_token, repo, gh_client)
        comment.edit(
            body=ButtonList(
                buttons=[
                    button
                    for button in button_list.buttons
                    if button.label not in selected_buttons
                ],
                title=RULES_TITLE,
            ).serialize()
        )
        if not rules:
            try:
                comment.delete()
            except Exception as e:
                logger.error(f"Error deleting comment: {e}")


def handle_revert(file_paths, pr_number, repo: Repository):
    pr = repo.get_pull(pr_number)
    branch_name = pr.head.ref if pr_number else pr.pr_head

    def get_contents_with_fallback(
        repo: Repository, file_path: str, branch: str = None
    ):
        try:
            if branch:
                return repo.get_contents(file_path, ref=branch)
            return repo.get_contents(file_path)
        except Exception:
            return None

    old_file_contents = [
        get_contents_with_fallback(repo, file_path) for file_path in file_paths
    ]
    for file_path, old_file_content in zip(file_paths, old_file_contents):
        try:
            current_content = repo.get_contents(file_path, ref=branch_name)
            if old_file_content:
                repo.update_file(
                    file_path,
                    f"Revert {file_path}",
                    old_file_content.decoded_content,
                    sha=current_content.sha,
                    branch=branch_name,
                )
            else:
                repo.delete_file(
                    file_path,
                    f"Delete {file_path}",
                    sha=current_content.sha,
                    branch=branch_name,
                )
        except Exception:
            pass  # file may not exist and this is expected


def handle_rules(request_dict, rules, user_token, repo: Repository, gh_client):
    pr = repo.get_pull(request_dict["issue"]["number"])
    chat_logger = (
        ChatLogger(
            {"username": request_dict["sender"]["login"]},
        )
        if MONGODB_URI
        else None
    )
    blocked_dirs = get_blocked_dirs(repo)
    comparison = repo.compare(pr.base.sha, pr.head.sha)  # head is the most recent
    commits_diff = comparison_to_diff(comparison, blocked_dirs)
    for rule in rules:
        changes_required, issue_title, issue_description = PostMerge(
            chat_logger=chat_logger
        ).check_for_issues(rule=rule, diff=commits_diff)
        if changes_required:
            new_pr = make_pr(
                title="[Sweep Rules] " + issue_title,
                repo_description=repo.description,
                summary=f"Apply this change: {rule}\n{issue_description}",
                repo_full_name=request_dict["repository"]["full_name"],
                installation_id=request_dict["installation"]["id"],
                user_token=user_token,
                use_faster_model=chat_logger.use_faster_model(gh_client),
                username=request_dict["sender"]["login"],
                chat_logger=chat_logger,
                branch_name=pr.head.ref,
                rule=rule,
            )
            pr.create_issue_comment(
                f"✨ **Created PR: {new_pr.html_url}** to fix `{rule}`.\n This PR was made against the `{pr.head.ref}` branch, not your main branch, so it's safe to merge if it looks good!"
            )
            posthog.capture(request_dict["sender"]["login"], "rule_pr_created")
