
from loguru import logger

from sweepai.core.chat import ChatGPT
from sweepai.core.context_pruning import (
    RepoContextManager,
    handle_function_call,
    sys_prompt,
    validate_and_parse_function_calls,
)
from sweepai.core.entities import Message

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

PLAN_SUBMITTED_MESSAGE = "SUCCESS: Report and plan submitted."
CLAUDE_MODEL = "claude-3-haiku-20240307"


def context_dfs(
    user_prompt: str,
    repo_context_manager: RepoContextManager,
) -> bool | None:
    max_iterations = 40
    repo_context_manager.current_top_snippets = []
    bad_call_count = 0
    # initial function call
    chat_gpt = ChatGPT()
    chat_gpt.messages = [Message(role="system", content=sys_prompt)]

    def perform_rollout():
        pass

    function_calls_string = chat_gpt.chat_anthropic(
        content=user_prompt,
        stop_sequences=["</function_call>"],
        model=CLAUDE_MODEL,
        message_key="user_request",
    )
    for _ in range(max_iterations):
        function_outputs = []
        function_calls = validate_and_parse_function_calls(
            function_calls_string, chat_gpt
        )
        for function_call in function_calls:
            function_output = handle_function_call(repo_context_manager, function_call)
            if PLAN_SUBMITTED_MESSAGE in function_output:
                return
            function_outputs.append(function_output)
        if len(function_calls) == 0:
            function_outputs.append(
                "No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n"
                + "<function_call>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</function_calls>"
            )
            bad_call_count += 1
            if bad_call_count >= 3:
                return
        function_calls_string = chat_gpt.chat_anthropic(
            content="\n\n".join(function_outputs),
            model=CLAUDE_MODEL,
            stop_sequences=["</function_call>"],
        )
    else:
        logger.warning(
            f"Context pruning iteration taking too long. Stopping after {max_iterations} iterations."
        )
    return


# general framework for a dfs search
# 1. sample trajectory
# 2. for each trajectory, run the assistant until it hits an error or end state
#    - in either case perform self-reflection
#    - update reflections section with current reflections
# 3. update the reflections section with the new reflections
