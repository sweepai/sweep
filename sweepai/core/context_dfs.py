import os
import subprocess
import urllib
from dataclasses import dataclass, field

import networkx as nx
import openai
from loguru import logger
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.config.client import SweepConfig
from sweepai.config.server import DEFAULT_GPT4_32K_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.context_dfs import modify_context
from sweepai.core.entities import Message, Snippet
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.convert_openai_anthropic import MockFunctionCall
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.modify_utils import post_process_rg_output
from sweepai.utils.openai_proxy import get_client
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.str_utils import FASTER_MODEL_MESSAGE
from sweepai.utils.tree_utils import DirectoryTree

state_eval_prompt = """You are helping contractors on a task that involves finding all of the relevant files needed to resolve an issue. This task does not involve writing or modifying code. The contractors' goal is to identify all necessary files, not actually implement the solution. Getting the files or adjacent code is sufficient, as long as all of the files have been found.
Respond using the following structured format:
<judgement_on_task>
Provide clear criteria for evaluating the contractor's performance, such as:
- Did they identify all relevant files needed to solve the issue? 
- Did they avoid including unnecessary or unrelated files?
- Did they demonstrate an understanding of the codebase and problem?
Examine each step and specifically call out anything done incorrectly with an explanation of the correct approach.
</judgement_on_task>
<overall_score>
Provide a clear rubric for the 1-10 scale, such as:
1-3: Failed to identify relevant files or understand the issue 
4-5: Identified some but not all required files
6-7: Found most relevant files but included some unnecessary ones
8-10: Successfully identified all and only the files needed to resolve the issue
</overall_score>
<message_to_contractor>
Provide a single sentence of extremely specific and actionable feedback, addressed directly to the contractor:
9-10: Great work identifying all the necessary files!
4-8: Focus on [specific files] and avoid [unnecessary files] to improve.
1-3: [Specific files] are not relevant. Look at [other files] instead.
</message_to_contractor>"""

def modify_context(
    chat_gpt: ChatGPT,
    user_prompt: str,
    repo_context_manager: RepoContextManager,
    ticket_progress: TicketProgress,
    model: str = "gpt-4-0125-preview",
) -> bool | None:
    max_iterations = 40
    repo_context_manager.current_top_snippets = []
    bad_call_count = 0
    # initial function call
    function_calls_string = chat_gpt.chat_anthropic(
        content=user_prompt,
        stop_sequences=["</function_call>"],
        model = CLAUDE_MODEL,
        message_key="user_request",
    )
    for _ in range(max_iterations):
        function_outputs = []
        function_calls = validate_and_parse_function_calls(function_calls_string, chat_gpt)
        for function_call in function_calls:
            function_output = handle_function_call(repo_context_manager, function_call)
            if PLAN_SUBMITTED_MESSAGE in function_output:
                return
            function_outputs.append(function_output)
        if len(function_calls) == 0:
            function_outputs.append("No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n"
                + "<function_call>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</function_calls>")
            bad_call_count += 1
            if bad_call_count >= 3:
                return
        function_calls_string = chat_gpt.chat_anthropic(
            content="\n\n".join(function_outputs),
            model=CLAUDE_MODEL,
            stop_sequences=["</function_call>"],
        )
        # if there is a message with a non-null key that's not saved, we can delete both it and it's preceding message
    else:
        logger.warning(
            f"Context pruning iteration taking too long. Stopping after {max_iterations} iterations."
        )
    logger.info(
        f"Context Management End:\ncurrent snippets to modify: {repo_context_manager.top_snippet_paths}\n current read only snippets: {repo_context_manager.relevant_read_only_snippet_paths}"
    )
    repo_context_manager.current_top_snippets = [
        snippet
        for snippet in repo_context_manager.current_top_snippets
        if snippet.file_path != "sweep.yaml"
    ]
    return

# general framework for a dfs search
# 1. sample trajectory
# 2. for each trajectory, run the assistant until it hits an error or end state
#    - in either case perform self-reflection
#    - update reflections section with current reflections
# 3. update the reflections section with the new reflections
