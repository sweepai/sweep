import traceback

import openai
from loguru import logger

from sweepai.core.entities import NoFilesException, Snippet
from sweepai.core.sweep_bot import SweepBot
from sweepai.handlers.on_review import get_pr_diffs_modified as get_pr_diffs
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.config.server import PREFIX, OPENAI_API_KEY, GITHUB_BOT_TOKEN
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import (
    get_github_client,
    search_snippets,
)
from sweepai.utils.prompt_constructor import HumanMessageCommentPrompt

github_access_token = GITHUB_BOT_TOKEN
openai.api_key = OPENAI_API_KEY

num_of_snippets_to_query = 30
total_number_of_snippet_tokens = 15_000
num_full_files = 2
num_extended_snippets = 2


def post_process_snippets(snippets: list[Snippet], max_num_of_snippets: int = 3):
    for snippet in snippets[:num_full_files]:
        snippet = snippet.expand()
