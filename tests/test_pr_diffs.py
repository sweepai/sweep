import os
from github import Github
from loguru import logger
import modal
from src.core.chat import DiffSummarization, PullRequestComment, format_for_anthropic
from src.core.prompts import review_prompt
from src.core.sweep_bot import SweepBot
from src.handlers.on_review import get_pr_diffs
from src.utils.constants import API_NAME, BOT_TOKEN_NAME

from src.utils.github_utils import get_file_contents, search_snippets
from src.utils.prompt_constructor import (
    HumanMessageFinalPRComment,
    HumanMessagePromptReview,
    HumanMessageReviewFollowup,
)
from src.utils.snippets import format_snippets

# Plan:
# 1. Get PR
# 2. Get files changed
# 3. Come up with some comments for the PR
# 4. Take comments and add them to the PR
stub = modal.Stub(API_NAME)
image = (
    modal.Image.debian_slim()
    .apt_install("git")
    .pip_install(
        "openai",
        "anthropic",
        "PyGithub",
        "loguru",
        "docarray",
        "backoff",
        "tiktoken",
        "highlight-io",
        "GitPython",
        "posthog",
        "tqdm",
    )
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("anthropic"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("highlight"),
]
FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 15 * 60,
}


def query_to_snippets_text(query, repo):
    snippets, tree = search_snippets(
        repo,
        f"{query}",
        num_files=10,
        installation_id=36855882,
    )
    snippets_text = format_snippets(snippets)
    return snippets_text, tree


query_to_snippets_fn = stub.function(**FUNCTION_SETTINGS, retries=0)(
    query_to_snippets_text
)

if __name__ == "__main__":
    access_token = os.environ.get("ACCESS_TOKEN")
    g = Github(access_token)
    repo_name = "sweepai/bot-internal"
    issue_url = "github.com/sweepai/bot-internal/issues/28"
    username = "wwzeng1"
    repo_description = "A repo for Sweep"
    title = "Sweep: Use loguru.info to show the number of tokens in the anthropic call"
    summary = ""
    replies_text = ""

    repo = g.get_repo(repo_name)
    pr = repo.get_pull(339)
    # Temp query
    query = pr.title
    logger.info("Getting PR diffs...")
    diffs = get_pr_diffs(repo, pr)
    with stub.run():
        logger.info("Getting snippets...")
        snippets_text, tree = query_to_snippets_fn.call(query, repo)
    human_message = HumanMessagePromptReview(
        repo_name=repo_name,
        issue_url=issue_url,
        username=username,
        repo_description=repo_description,
        title=title,
        summary=summary + replies_text,
        snippets=snippets_text,
        tree=tree,
        diffs=[diffs[0]],
        pr_title=pr.title,
        pr_message=pr.body or "",
    )  # Anything in repo tree that has something going through is expanded
    sweep_bot = SweepBot.from_system_message_content(
        # human_message=human_message, model="claude-v1.3-100k", repo=repo, is_reply=False
        human_message=human_message,
        repo=repo,
        is_reply=False,
    )
    # write human message to file
    summarization_replies = []
    with open("tests/data/human_message.txt", "w+") as f:
        f.write(format_for_anthropic(sweep_bot.messages))
    summarization_reply = sweep_bot.chat(review_prompt, message_key="review")
    extracted_summary = DiffSummarization.from_string(summarization_reply)
    summarization_replies.append(extracted_summary.content)
    # comment = PullRequestComment.from_string(reply)
    for diff in diffs[1:]:
        review_message = HumanMessageReviewFollowup(diff=diff)
        review_prompt_constructed = review_message.construct_prompt()
        summarization_reply = sweep_bot.chat(
            review_prompt_constructed, message_key="review"
        )
        extracted_summary = DiffSummarization.from_string(summarization_reply)
        summarization_replies.append(extracted_summary.content)
    final_review_prompt = HumanMessageFinalPRComment(
        summarization_replies=summarization_replies
    ).construct_prompt()
    reply = sweep_bot.chat(final_review_prompt, message_key="final_review")
    review_coment = PullRequestComment.from_string(reply)
    pr.create_review(body=review_coment.content, event="COMMENT", comments=[])
