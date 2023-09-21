"""
Take a PR and provide an AI generated review of the PR.
"""
from logn import logger

from sweepai.config.server import MONGODB_URI
from sweepai.core.entities import DiffSummarization, PullRequestComment
from sweepai.core.prompts import review_prompt
from sweepai.core.sweep_bot import SweepBot
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.prompt_constructor import (
    HumanMessageFinalPRComment,
    HumanMessagePromptReview,
)


# Plan:
# 1. Get PR
# 2. Get files changed
# 3. Come up with some comments for the PR
# 4. Take comments and add them to the PR


def get_pr_diffs(repo, pr):
    base_sha = pr.base.sha
    head_sha = pr.head.sha

    comparison = repo.compare(base_sha, head_sha)
    file_diffs = comparison.files

    pr_diffs = []
    for file in file_diffs:
        diff = file.patch
        if file.status not in ["added", "modified", "removed", "renamed"]:
            logger.info(
                f"File status {file.status} not recognized"
            )
        else:
            pr_diffs.append((file.filename, diff))
    return pr_diffs


class PRDetails:
    def __init__(self, repo, issue_url, username, repo_description, title, summary, replies_text, tree, plan):
        self.repo = repo
        self.issue_url = issue_url
        self.username = username
        self.repo_description = repo_description
        self.title = title
        self.summary = summary
        self.replies_text = replies_text
        self.tree = tree
        self.plan = plan

def review_pr(
    pr_details,
    pr,
    lint_output=None,
    chat_logger=None,
):
    repo_name = pr_details.repo.full_name
    logger.info("Getting PR diffs...")
    diffs = get_pr_diffs(pr_details.repo, pr)
    if len(diffs) == 0:
        logger.info("No diffs found.")
        return False, None
    human_message = HumanMessagePromptReview(
        repo_name=repo_name,
        issue_url=pr_details.issue_url,
        username=pr_details.username,
        repo_description=pr_details.repo_description,
        title=pr_details.title,
        summary=pr_details.summary + pr_details.replies_text,
        snippets=[],
        tree=pr_details.tree,
        diffs=diffs,
        pr_title=pr.title,
        pr_message=pr.body or "",
        plan=pr_details.plan,
    )

    summarization_replies = []

    chat_logger = (
        chat_logger
        if chat_logger is not None
        else ChatLogger(
            {
                "repo_name": repo_name,
                "title": "(Review) " + pr_details.title,
                "summary": pr_details.summary + pr_details.replies_text,
                "issue_url": pr_details.issue_url,
                "username": pr_details.username,
                "repo_description": pr_details.repo_description,
                "tree": pr_details.tree,
                "type": "review",
            }
        )
        if MONGODB_URI
        else None
    )
    sweep_bot = SweepBot.from_system_message_content(
        human_message=human_message,
        repo=pr_details.repo,
        is_reply=False,
        chat_logger=chat_logger,
    )
    summarization_reply = sweep_bot.chat(
        review_prompt.format(
            repo_name=repo_name,
            repo_description=pr_details.repo_description,
            issue_url=pr_details.issue_url,
            username=pr_details.username,
            title=pr_details.title,
            description=pr_details.summary + pr_details.replies_text,
        ),
        message_key="review",
    )
    extracted_summary = DiffSummarization.from_string(summarization_reply)
    summarization_replies.append(extracted_summary.content)
    final_review_prompt = HumanMessageFinalPRComment(
        summarization_replies=summarization_replies
    ).construct_prompt()

    reply = sweep_bot.chat(final_review_prompt, message_key="final_review")
    review_comment = PullRequestComment.from_string(reply)
    pr.create_review(body=review_comment.content, event="COMMENT", comments=[])
    changes_required = "yes" in review_comment.changes_required.lower()
    logger.info(f"Changes required: {changes_required}")
    return changes_required, review_comment.content
