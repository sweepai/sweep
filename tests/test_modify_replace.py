import re

from sweepai.utils.diff import sliding_window_replacement

file_contents = r'''
# TODO: Add file validation

import math
import re
import traceback
import openai

import github
from github import GithubException, BadCredentialsException
from tabulate import tabulate
from tqdm import tqdm

from logn import logger, LogTask
from sweepai.core.context_pruning import ContextPruning
from sweepai.core.documentation_searcher import extract_relevant_docs
from sweepai.core.entities import (
    ProposedIssue,
    SandboxResponse,
    Snippet,
    NoFilesException,
    SweepContext,
    MaxTokensExceeded,
    EmptyRepository,
)
from sweepai.core.external_searcher import ExternalSearcher
from sweepai.core.slow_mode_expand import SlowModeBot
from sweepai.core.sweep_bot import SweepBot
from sweepai.core.prompts import issue_comment_prompt

# from sandbox.sandbox_utils import Sandbox
from sweepai.handlers.create_pr import (
    create_pr_changes,
    create_config_pr,
    safe_delete_sweep_branch,
)
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_review import review_pr
from sweepai.utils.buttons import create_action_buttons
from sweepai.utils.chat_logger import ChatLogger
from sweepai.config.client import (
    SweepConfig,
    get_documentation_dict,
)
from sweepai.config.server import (
    ENV,
    MONGODB_URI,
    OPENAI_API_KEY,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_NAME,
    OPENAI_USE_3_5_MODEL_ONLY,
    WHITELISTED_REPOS,
)
from sweepai.utils.ticket_utils import *
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.search_utils import search_snippets
from sweepai.utils.tree_utils import DirectoryTree

openai.api_key = OPENAI_API_KEY

sweeping_gif = """<img src="https://raw.githubusercontent.com/sweepai/sweep/main/.assets/sweeping.gif" width="100" style="width:50px; margin-bottom:10px" alt="Sweeping">"""


def center(text: str) -> str:
    return f"<div align='center'>{text}</div>"
'''

updated_snippet = r'''
sweeping_gif = """
<div class="swing">
    <img src="https://raw.githubusercontent.com/sweepai/sweep/main/.assets/sweeping.gif" width="100" style="width:50px; margin-bottom:10px" alt="Sweeping">
</div>
<style>
.swing {
    animation: swing ease-in-out 1s infinite alternate;
    transform-origin: center -20px;
    float:left;
    box-shadow: 5px 5px 10px rgba(0,0,0,0.5);
}
@keyframes swing {
    0% { transform: rotate(3deg); }
    100% { transform: rotate(-3deg); }
}
</style>
"""
'''

selected_snippet = r'''
sweeping_gif = """<img src="https://raw.githubusercontent.com/sweepai/sweep/main/.assets/sweeping.gif" width="100" style="width:50px; margin-bottom:10px" alt="Sweeping">"""
'''.strip()


def match_indent(generated: str, original: str) -> str:
    indent_type = "\t" if "\t" in original[:5] else " "
    generated_indents = len(generated) - len(generated.lstrip())
    target_indents = len(original) - len(original.lstrip())
    diff_indents = target_indents - generated_indents
    if diff_indents > 0:
        generated = indent_type * diff_indents + generated.replace(
            "\n", "\n" + indent_type * diff_indents
        )
    return generated


def main():
    result = file_contents
    result, _, _ = sliding_window_replacement(
        result.splitlines(),
        selected_snippet.splitlines(),
        match_indent(updated_snippet, selected_snippet).splitlines(),
    )
    result = "\n".join(result)

    ending_newlines = len(file_contents) - len(file_contents.rstrip("\n"))
    result = result.rstrip("\n") + "\n" * ending_newlines
    print(result)


main()
