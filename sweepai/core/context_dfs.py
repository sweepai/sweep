
from copy import deepcopy
import re
from loguru import logger
import openai

from sweepai.core.chat import ChatGPT
from sweepai.core.context_pruning import (
    RepoContextManager,
    add_relevant_files_to_top_snippets,
    build_import_trees,
    handle_function_call,
    parse_query_for_files,
    sys_prompt,
    validate_and_parse_function_calls,
    unformatted_user_prompt,

)
from sweepai.core.entities import Message
from sweepai.utils.github_utils import ClonedRepo

response_format = """Respond using the following structured format:
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

state_eval_prompt = """You are helping contractors on a task that involves finding all of the relevant files needed to resolve an issue. This task does not involve writing or modifying code. The contractors' goal is to identify all necessary files, not actually implement the solution. Getting the files or adjacent code is sufficient, as long as all of the files have been found.
""" + response_format

class EvaluatorAgent(ChatGPT):
    def evaluate_run(self, run_text: str):
        self.model = CLAUDE_MODEL
        self.messages = [Message(role="system", content=state_eval_prompt)]
        evaluate_response = self.chat_anthropic(
            content=run_text + "\n\n" + response_format,
            stop_sequences=["</message_to_contractor>"],
            model=CLAUDE_MODEL,
            message_key="user_request",
        )

        overall_score = None
        message_to_contractor = None
        overall_score_pattern = r"<overall_score>(.*?)</overall_score>"
        message_to_contractor_pattern = r"<message_to_contractor>(.*?)</message_to_contractor>"

        overall_score_match = re.search(overall_score_pattern, evaluate_response, re.DOTALL)
        message_to_contractor_match = re.search(message_to_contractor_pattern, evaluate_response, re.DOTALL)

        if overall_score_match is None or message_to_contractor_match is None:
            return overall_score, message_to_contractor

        overall_score = overall_score_match.group(1).strip()
        # check if 1 through 10 are a match
        if not re.match(r"^[1-9]|10$", overall_score):
            return None, None
        
        overall_score = int(overall_score)

        message_to_contractor = message_to_contractor_match.group(1).strip()
        return overall_score, message_to_contractor

PLAN_SUBMITTED_MESSAGE = "SUCCESS: Report and plan submitted."
CLAUDE_MODEL = "claude-3-haiku-20240307"


def context_dfs(
    user_prompt: str,
    repo_context_manager: RepoContextManager,
) -> bool | None:
    max_iterations = 40
    repo_context_manager.current_top_snippets = []
    # initial function call
    def perform_rollout(repo_context_manager: RepoContextManager):
        chat_gpt = ChatGPT()
        chat_gpt.messages = [Message(role="system", content=sys_prompt)]
        function_calls_string = chat_gpt.chat_anthropic(
            content=user_prompt,
            stop_sequences=["</function_call>"],
            model=CLAUDE_MODEL,
            message_key="user_request",
        )
        bad_call_count = 0
        for _ in range(max_iterations):
            function_calls = validate_and_parse_function_calls(
                function_calls_string, chat_gpt
            )
            for function_call in function_calls:
                function_output = handle_function_call(repo_context_manager, function_call)
                if PLAN_SUBMITTED_MESSAGE in function_output:
                    return chat_gpt.messages
            if len(function_calls) == 0:
                function_output = "No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n" \
                    + "<function_call>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</function_calls>"
                bad_call_count += 1
                if bad_call_count >= 2:
                    return chat_gpt.messages
            function_calls_string = chat_gpt.chat_anthropic(
                content=function_output,
                model=CLAUDE_MODEL,
                stop_sequences=["</function_call>"],
            )
        return chat_gpt.messages
    for _ in range(3):
        # operate on a deep copy of the repo context manager
        copied_repo_context_manager = deepcopy(repo_context_manager)
        message_results = perform_rollout(copied_repo_context_manager)
        truncated_message_results = message_results[1:] # skip system prompt
        overall_score, message_to_contractor = EvaluatorAgent().evaluate_run("\n\n".join([truncated_message_results]))
        import pdb; pdb.set_trace()
    return


# general framework for a dfs search
# 1. sample trajectory
# 2. for each trajectory, run the assistant until it hits an error or end state
#    - in either case perform self-reflection
#    - update reflections section with current reflections
# 3. update the reflections section with the new reflections

def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    seed: int = None,
):
    logger.info("Seed: " + str(seed))
    try:
        # attempt to get import tree for relevant snippets that show up in the query
        repo_context_manager, import_graph = parse_query_for_files(
            query, repo_context_manager
        )
        # for any code file mentioned in the query, build its import tree - This is currently not used
        repo_context_manager = build_import_trees(
            repo_context_manager,
            import_graph,
        )
        # for any code file mentioned in the query add it to the top relevant snippets
        repo_context_manager = add_relevant_files_to_top_snippets(repo_context_manager)
        # add relevant files to dir_obj inside repo_context_manager, this is in case dir_obj is too large when as a string
        repo_context_manager.dir_obj.add_relevant_files(
            repo_context_manager.relevant_file_paths
        )

        user_prompt = repo_context_manager.format_context(
            unformatted_user_prompt=unformatted_user_prompt,
            query=query,
        )
        chat_gpt = ChatGPT()
        chat_gpt.messages = [Message(role="system", content=sys_prompt)]
        old_top_snippets = [
            snippet for snippet in repo_context_manager.current_top_snippets
        ]
        try:
            context_dfs(
                user_prompt,
                repo_context_manager,
            )
        except openai.BadRequestError as e:  # sometimes means that run has expired
            logger.exception(e)
        if len(repo_context_manager.current_top_snippets) == 0:
            repo_context_manager.current_top_snippets = old_top_snippets
        return repo_context_manager
    except Exception as e:
        logger.exception(e)
        return repo_context_manager

if __name__ == "__main__":
    try:
        from sweepai.utils.github_utils import get_installation_id
        from sweepai.utils.ticket_utils import prep_snippets
        
        organization_name = "sweepai"
        installation_id = get_installation_id(organization_name)
        cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")
        query = "rename all instances of call_openai to chat_openai in the codebase"
        # golden response is
        repo_context_manager = prep_snippets(cloned_repo, query)
        rcm = get_relevant_context(
            query,
            repo_context_manager,
        )
        for snippet in rcm.current_top_snippets:
            print(snippet.denotation)
    except Exception as e:
        import sys
        info = sys.exc_info()
        import pdb;
        pdb.post_mortem(info[2])
        raise e