import time

import modal
from sweepai.config.server import API_MODAL_INST_NAME, ENV
from sweepai.core.entities import FileChangeRequest, SweepContext
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_ticket import post_process_snippets
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.diff import generate_new_file_from_patch
from sweepai.utils.github_utils import get_github_client, search_snippets
from sweepai.utils.prompt_constructor import HumanMessagePrompt

title = "Sweep: Fix Uncaught SyntaxError: Unexpected token '&' (at examples:14:21)."
summary = "None"

stub = modal.Stub(API_MODAL_INST_NAME)
stub.pr_queues = modal.Dict.new()  # maps (repo_full_name, pull_request_ids) -> queues
stub.issue_lock = modal.Dict.new()  # maps (repo_full_name, issue_number) -> process id
image = (
    modal.Image.debian_slim()
    .apt_install("git", "universal-ctags")
    .run_commands('export PATH="/usr/local/bin:$PATH"')
    .pip_install(
        "openai",
        "anthropic",
        "PyGithub",
        "loguru",
        "docarray",
        "backoff",
        "tiktoken",
        "GitPython",
        "posthog",
        "tqdm",
        "pyyaml",
        "pymongo",
        "tabulate",
        "redis",
        "llama_index",
        "bs4",
        "e2b==0.1.10",
        # for docs search
        "deeplake",
        "robotexclusionrulesparser",
        "playwright",
        "markdownify",
        "geopy",
        "rapidfuzz",
    )
)
secrets = [
    modal.Secret.from_name("bot-token"),
    modal.Secret.from_name("github"),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("anthropic"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("mongodb"),
    modal.Secret.from_name("discord"),
    modal.Secret.from_name("redis_url"),
    modal.Secret.from_name("e2b"),
    modal.Secret.from_name("gdrp"),
]

FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 60 * 60,
    "keep_warm": 1,
}


@stub.local_entrypoint()
def benchmark_modify_file(file_change_request, title, summary, repo_full_name):
    from sweepai.config.server import REDIS_URL

    print("REDIS_URL:", REDIS_URL)
    installation_id = 36855882
    user_token, g = get_github_client(installation_id)

    repo = g.get_repo(repo_full_name)
    repo_name = repo_full_name.split("/")[-1]
    issue_number = 1367
    issue_url = "https://github.com/sweepai/sweep/issues/1367"
    repo_description = repo.description
    # Create a HumanMessagePrompt object with placeholder values
    human_message = HumanMessagePrompt(
        repo_name=repo_name,
        issue_url=issue_url,
        username="wwzeng1",
        repo_description=repo_description,
        title=title,
        summary="",
        snippets=[],
        tree="",
    )
    chat_logger = ChatLogger(
        {
            "repo_name": repo_name,
            "title": title,
            "summary": summary,
            "issue_number": issue_number,
            "issue_url": issue_url,
            "username": "wwzeng1",
            "repo_full_name": repo_full_name,
            "repo_description": repo_description,
            "installation_id": installation_id,
            "type": "ticket",
            "mode": ENV,
            "comment_id": None,
            "edited": False,
        }
    )

    # Generate the context for the SweepBot
    sweep_context = SweepContext(
        issue_url=issue_url,
        use_faster_model=False,
    )
    # Call the process_file function with the generated context
    sweep_bot = SweepBot.from_system_message_content(
        human_message=human_message,
        repo=repo,
        is_reply=None,
        chat_logger=chat_logger,
        sweep_context=sweep_context,
    )
    file_change_request = FileChangeRequest(
        filename="examples/README.md",
        file_content="import logging",
        change_type="modify",
        instructions="import logging",
    )
    import pdb

    pdb.set_trace()
    sweep_bot.modify_file()

    new_file, errors = generate_new_file_from_patch(
        modify_file_response,
        contents,
        chunk_offset=chunk_offset,
        sweep_context=self.sweep_context,
    )
    # Record the end time


if __name__ == "__main__":
    benchmark_modify_file(None, title, summary, "sweepai/sweep")
