import copy
import re
import traceback
from collections import OrderedDict
import requests
from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from pydantic import BaseModel
from sweepai.agents.complete_code import ExtractLeftoverComments
from sweepai.agents.graph_child import (
    GraphChildBot,
    GraphContextAndPlan,
    extract_python_span,
)
from sweepai.agents.graph_parent import GraphParentBot
from sweepai.agents.prune_modify_snippets import PruneModifySnippets
from sweepai.agents.validate_code import ChangeValidation, ChangeValidator
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DEBUG, SANDBOX_URL, SECONDARY_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import (
    FileChangeRequest,
    FileCreation,
    MaxTokensExceeded,
    Message,
    NoFilesException,
    ProposedIssue,
    PullRequest,
    RegexMatchError,
    SandboxResponse,
    SectionRewrite,
    Snippet,
    UnneededEditError,
)
from sweepai.core.prompts import (
    create_file_prompt,
    dont_use_chunking_message,
    fetch_snippets_prompt,
    fetch_snippets_system_prompt,
    files_to_change_prompt,
    pull_request_prompt,
    python_files_to_change_prompt,
    rewrite_file_prompt,
    rewrite_file_system_prompt,
    snippet_replacement,
    snippet_replacement_system_message,
    subissues_prompt,
    update_snippets_prompt,
    update_snippets_system_prompt,
    use_chunking_message,
)
from sweepai.logn import logger
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.diff import format_contents, generate_diff, is_markdown
from sweepai.utils.function_call_utils import find_function_calls
from sweepai.utils.graph import Graph
from sweepai.utils.search_and_replace import (
    Match,
    find_best_match,
    match_indent,
    split_ellipses,
)
from sweepai.utils.utils import chunk_code
from sweepai.agents.modify_bot import ModifyBot
