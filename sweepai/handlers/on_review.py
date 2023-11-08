"""
Take a PR and provide an AI generated review of the PR.
"""
from sweepai.config.server import MONGODB_URI
from sweepai.core.entities import PullRequestComment
from sweepai.core.prompts import final_review_prompt, review_prompt
from sweepai.core.sweep_bot import SweepBot
from sweepai.logn import logger
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.prompt_constructor import HumanMessagePromptReview


def get_pr_diffs(repo, pr):
    base_sha = pr.base.sha
    head_sha = pr.head.sha

    comparison = repo.compare(base_sha, head_sha)
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
    return pr_diffs


def review_pr(
    repo,
    pr,
    issue_url,
    username,
    repo_description,
    title,
    summary,
    replies_text,
    tree,
    commit_history,
    plan,
    lint_output=None,
    chat_logger=None,
):
    repo_name = repo.full_name
    logger.info("Getting PR diffs...")
    diffs = get_pr_diffs(repo, pr)
    if len(diffs) == 0:
        logger.info("No diffs found.")
        return False, ""
    human_message = HumanMessagePromptReview(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary + replies_text,
        snippets=[],
        tree=tree,
        commit_history=commit_history,
        diffs=diffs,
        pr_title=pr.title,
        pr_message=pr.body or "",
        plan=plan,
    )

    chat_logger = (
        chat_logger
        if chat_logger is not None
        else ChatLogger(
            {
                "repo_name": repo_name,
                "title": "(Review) " + title,
                "summary": summary + replies_text,
                "issue_url": issue_url,
                "username": username,
                "repo_description": repo_description,
                "issue_url": issue_url,
                "username": username,
                "repo_description": repo_description,
                "title": title,
                "summary": summary,
                "replies_text": replies_text,
                "tree": tree,
                "type": "review",
            }
        )
        if MONGODB_URI
        else None
    )
    sweep_bot = SweepBot.from_system_message_content(
        human_message=human_message,
        repo=repo,
        is_reply=False,
        chat_logger=chat_logger,
    )
    sweep_bot.chat(
        review_prompt.format(
            repo_name=repo_name,
            repo_description=repo_description,
            issue_url=issue_url,
            username=username,
            title=title,
            description=summary + replies_text,
        ),
        message_key="review",
    )
    reply = sweep_bot.chat(final_review_prompt, message_key="final_review")
    review_comment = PullRequestComment.from_string(reply)
    pr.create_review(body=review_comment.content, event="COMMENT", comments=[])
    changes_required = "yes" in review_comment.changes_required.lower()
    return changes_required, review_comment.content
