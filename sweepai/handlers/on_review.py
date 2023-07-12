"""
Take a PR and provide an AI generated review of the PR.
"""
from loguru import logger

from sweepai.core.entities import DiffSummarization, PullRequestComment
from sweepai.core.prompts import review_prompt
from sweepai.core.sweep_bot import SweepBot
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import get_file_contents
from sweepai.utils.prompt_constructor import HumanMessageFinalPRComment, HumanMessagePromptReview, \
    HumanMessageReviewFollowup


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
        print(file.status)
        diff = file.patch
        if file.status == "added":
            pr_diffs.append((file.filename, get_file_contents(repo, file_path=file.filename, ref=head_sha), "", diff))
        elif file.status == "modified":
            pr_diffs.append((file.filename, get_file_contents(repo, file_path=file.filename, ref=head_sha),
                             get_file_contents(repo, file_path=file.filename, ref=base_sha), diff))
        elif file.status == "removed":
            pr_diffs.append((file.filename, "", get_file_contents(repo, file_path=file.filename, ref=base_sha), diff))
        else:
            logger.info(f"File status {file.status} not recognized")  # TODO(sweep): We don't handle renamed files
    return pr_diffs


def review_pr(repo, pr, issue_url, username, repo_description, title, summary, replies_text, tree):
    repo_name = repo.full_name
    logger.info("Getting PR diffs...")
    diffs = get_pr_diffs(repo, pr)
    human_message = HumanMessagePromptReview(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary + replies_text,
        snippets=[],
        tree=tree,
        diffs=[diffs[0] if len(diffs) > 0 else ""],
        pr_title=pr.title,
        pr_message=pr.body or "",
    )
    summarization_replies = []

    chat_logger = ChatLogger({
        'repo_name': repo_name,
        'title': '(Review) ' + title,
        'summary': summary + replies_text,
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
    })
    sweep_bot = SweepBot.from_system_message_content(
        # human_message=human_message, model="claude-v1.3-100k", repo=repo, is_reply=False
        human_message=human_message, repo=repo, is_reply=False, chat_logger=chat_logger
    )
    summarization_reply = sweep_bot.chat(review_prompt, message_key="review")
    extracted_summary = DiffSummarization.from_string(summarization_reply)
    summarization_replies.append(extracted_summary.content)
    for diff in diffs[1:]:
        review_message = HumanMessageReviewFollowup(diff=diff)
        review_prompt_constructed = review_message.construct_prompt()
        summarization_reply = sweep_bot.chat(review_prompt_constructed, message_key="review")
        extracted_summary = DiffSummarization.from_string(summarization_reply)
        summarization_replies.append(extracted_summary.content)
    final_review_prompt = HumanMessageFinalPRComment(summarization_replies=summarization_replies).construct_prompt()
    reply = sweep_bot.chat(final_review_prompt, message_key="final_review")
    review_comment = PullRequestComment.from_string(reply)
    pr.create_review(body=review_comment.content, event="COMMENT", comments=[])
    changes_required = 'yes' in review_comment.changes_required.lower()
    return changes_required, review_comment.content
