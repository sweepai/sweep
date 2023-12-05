import json
import re
import time
from copy import deepcopy

from attr import dataclass
from loguru import logger
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.agents.assistant_wrapper import client, openai_retry_with_timeout
from sweepai.core.entities import Snippet
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.tree_utils import DirectoryTree

ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens

sys_prompt = """You are a brilliant engineer assigned to the following Github issue. You are currently gathering the minimum set of information that allows you to plan the solution to the issue. It is very important that you get this right.

Reply in the following format:

<contextual_request_analysis>
Use the snippets, issue metadata and other information to determine the information that is critical to solve the issue. For each snippet, identify whether it was a true positive or a false positive.
Propose the most important paths as well as any new required paths, along with a justification.
</contextual_request_analysis>

Then use the store_file_path and expand_directory tools to optimize the snippets_in_repo, repo_tree, and paths_in_repo until they allow you to perfectly solve the user request. 
If you expand a directory, you automatically expand all of its subdirectories, so do not list its subdirectories. Store all files or directories that are referenced in the issue title or descriptions.
Store as few file paths as necessary to solve the user request."""

unformatted_user_prompt = """\
<snippets_in_repo>
{snippets_in_repo}
</snippets_in_repo>
<paths_in_repo>
{paths_in_repo}
</paths_in_repo>
<repo_tree>
{repo_tree}
</repo_tree>
# Instructions
## User Request
{query}
The above <repo_tree> <snippets_in_repo> and <paths_in_repo> have unnecessary information. Modify paths_in_repo, snippets_in_repo, and repo_tree to store only the absolutely necessary information.

Reply in the following format:

<contextual_request_analysis>
Use the snippets, issue metadata and other information to determine the information that is critical to solve the issue. For each snippet, identify whether it was a true positive or a false positive.
Propose the most important paths as well as any new required paths, along with a justification.
</contextual_request_analysis>

Then use the store_file_path and expand_directory tools to optimize the snippets_in_repo, repo_tree, and paths_in_repo until they allow you to perfectly solve the user request. 
If you expand a directory, you automatically expand all of its subdirectories, so do not list its subdirectories. Store all files or directories that are referenced in the issue title or descriptions.
Store as few file paths as necessary to solve the user request."""

functions = [
    {
        "name": "store_file_path",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File or directory to store.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for store the file_path.",
                },
            },
            "required": ["file_path", "justification"],
        },
        "description": "Use this to either store an existing file_path or add a new path to paths_in_repo. Only store paths you are certain are relevant to solving the user request. All of the files not listed will be removed from the paths_in_repo. Make sure to store ALL of the files that are referenced in the issue title or description.",
    },
    {
        "name": "expand_directory",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {
                    "type": "string",
                    "description": "Directory to expand",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for expanding the directory.",
                },
            },
            "required": ["directory_path", "justification"],
        },
        "description": "Expand an existing directory that is closed. This is used for exploration only and does not affect the snippets.",
    },
]

tools = [
    {"type": "function", "function": functions[0]},
    {"type": "function", "function": functions[1]},
]


@staticmethod
def can_add_snippet(snippet: Snippet, current_snippets: list[Snippet]):
    return (
        len(snippet.xml) + sum([len(snippet.xml) for snippet in current_snippets])
        <= ASSISTANT_MAX_CHARS
    )


@dataclass
class RepoContextManager:
    dir_obj: DirectoryTree
    current_top_tree: str
    snippets: list[Snippet]
    snippet_scores: dict[str, float]
    current_top_snippets: list[Snippet] = []

    @property
    def top_snippet_paths(self):
        return [snippet.file_path for snippet in self.current_top_snippets]

    def remove_all_non_kept_paths(self, paths_to_keep: list[str]):
        self.current_top_snippets = [
            snippet
            for snippet in self.current_top_snippets
            if any(
                snippet.file_path.startswith(path_to_keep)
                for path_to_keep in paths_to_keep
            )
        ]
        self.dir_obj.remove_all_not_included(paths_to_keep)

    def expand_all_directories(self, directories_to_expand: list[str]):
        self.dir_obj.expand_directory(directories_to_expand)

    def is_path_valid(self, path: str, directory: bool = False):
        if directory:
            return any(snippet.file_path.startswith(path) for snippet in self.snippets)
        return any(snippet.file_path == path for snippet in self.snippets)

    def format_context(
        self,
        unformatted_user_prompt: str,
        query: str,
    ):
        new_top_snippets: list[Snippet] = []
        for snippet in self.current_top_snippets:
            if can_add_snippet(snippet, new_top_snippets):
                new_top_snippets.append(snippet)
        self.current_top_snippets = new_top_snippets
        top_snippets_str = [snippet.xml for snippet in self.current_top_snippets]
        paths_in_repo = [snippet.file_path for snippet in self.current_top_snippets]
        snippets_in_repo_str = "\n".join(top_snippets_str)
        paths_in_repo_str = "\n".join(paths_in_repo)
        repo_tree = str(self.dir_obj)
        user_prompt = unformatted_user_prompt.format(
            query=query,
            snippets_in_repo=snippets_in_repo_str,
            paths_in_repo=paths_in_repo_str,
            repo_tree=repo_tree,
        )
        return user_prompt

    def get_highest_scoring_snippet(self, file_path: str) -> Snippet:
        snippet_key = (
            lambda snippet: f"{snippet.file_path}:{snippet.start}:{snippet.end}"
        )
        filtered_snippets = [
            snippet
            for snippet in self.snippets
            if snippet.file_path == file_path
            and snippet not in self.current_top_snippets
        ]
        if not filtered_snippets:
            return None
        highest_scoring_snippet = max(
            filtered_snippets,
            key=lambda snippet: self.snippet_scores[snippet_key(snippet)]
            if snippet_key(snippet) in self.snippet_scores
            else 0,
        )
        return highest_scoring_snippet

    def add_file_paths(self, paths_to_add: list[str]):
        self.dir_obj.add_file_paths(paths_to_add)
        for file_path in paths_to_add:
            highest_scoring_snippet = self.get_highest_scoring_snippet(file_path)
            if highest_scoring_snippet is None:
                continue
            if can_add_snippet(highest_scoring_snippet, self.current_top_snippets):
                self.current_top_snippets.append(highest_scoring_snippet)
                continue
            # otherwise try adding it by removing others
            prev_top_snippets = deepcopy(self.current_top_snippets)
            self.current_top_snippets = [highest_scoring_snippet]
            for snippet in prev_top_snippets:
                if can_add_snippet(snippet, self.current_top_snippets):
                    self.current_top_snippets.append(snippet)


@file_cache(ignore_params=["repo_context_manager", "ticket_progress", "chat_logger"])
def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    ticket_progress: TicketProgress | None = None,
    chat_logger: ChatLogger = None,
):
    modify_iterations: int = 2
    model = "gpt-3.5-turbo-1106" if (chat_logger and chat_logger.use_faster_model()) else "gpt-4-1106-preview"
    try:
        user_prompt = repo_context_manager.format_context(
            unformatted_user_prompt=unformatted_user_prompt,
            query=query,
        )
        assistant = openai_retry_with_timeout(
            client.beta.assistants.create,
            name="Relevant Files Assistant",
            instructions=sys_prompt,
            tools=tools,
            model=model,
        )
        thread = openai_retry_with_timeout(client.beta.threads.create)
        _ = openai_retry_with_timeout(
            client.beta.threads.messages.create,
            thread.id,
            role="user",
            content=f"{user_prompt}",
        )
        run = openai_retry_with_timeout(
            client.beta.threads.runs.create,
            thread_id=thread.id,
            assistant_id=assistant.id,
        )
        done = modify_context(thread, run, repo_context_manager, ticket_progress)
        ticket_progress.search_progress.pruning_conversation_counter = 1
        if done:
            return repo_context_manager
        for i in range(modify_iterations):
            ticket_progress.search_progress.pruning_conversation_counter = i + 1
            thread = openai_retry_with_timeout(client.beta.threads.create)
            user_prompt = repo_context_manager.format_context(
                unformatted_user_prompt=unformatted_user_prompt, query=query
            )
            _ = openai_retry_with_timeout(
                client.beta.threads.messages.create,
                thread.id,
                role="user",
                content=f"{user_prompt}\nIf the current snippets_in_repo, repo_tree, and paths_in_repo allow you to solve the issue, store all of the existing file paths.",
            )
            run = openai_retry_with_timeout( 
                client.beta.threads.runs.create,
                thread_id=thread.id,
                assistant_id=assistant.id,
            )
            done = modify_context(thread, run, repo_context_manager, ticket_progress)
            if done:
                break
        return repo_context_manager
    except Exception as e:
        logger.exception(e)
        return repo_context_manager


def modify_context(
    thread: Thread,
    run: Run,
    repo_context_manager: RepoContextManager,
    ticket_progress: TicketProgress,
) -> bool | None:
    max_iterations: int = int(
        30
    )
    paths_to_keep = []  # consider persisting these across runs
    paths_to_add = []
    directories_to_expand = []
    logger.info(
        f"Context Management Start:\ncurrent snippet paths: {repo_context_manager.top_snippet_paths}"
    )
    initial_file_paths = repo_context_manager.top_snippet_paths
    for iter in range(max_iterations):
        run = openai_retry_with_timeout(
            client.beta.threads.runs.retrieve,
            thread_id=thread.id,
            run_id=run.id,
        )
        if iter % 5 == 0:
            assistant_conversation = AssistantConversation.from_ids(
                assistant_id=run.assistant_id,
                run_id=run.id,
                thread_id=thread.id,
            )
            if assistant_conversation:
                ticket_progress.search_progress.pruning_conversation = (
                    assistant_conversation
                )
            ticket_progress.search_progress.repo_tree = str(repo_context_manager.dir_obj)
            ticket_progress.search_progress.final_snippets = (
                repo_context_manager.current_top_snippets
            )
            logger.info("iteration: " + str(iter))
            ticket_progress.save()
        if run.status == "completed":
            break
        if (
            run.status != "requires_action"
            or run.required_action is None
            or run.required_action.submit_tool_outputs is None
            or run.required_action.submit_tool_outputs.tool_calls is None
        ):
            time.sleep(3)
            continue
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []
        for tool_call in tool_calls:
            try:
                tool_call_arguments = re.sub(r"\\+'", "", tool_call.function.arguments)
                function_input = json.loads(tool_call_arguments)
            except:
                logger.warning(
                    f"Could not parse function arguments: {tool_call_arguments}"
                )
                tool_outputs.append(
                    {
                        "tool_call_id": tool_call.id,
                        "output": "FAILURE: Could not parse function arguments.",
                    }
                )
                continue
            function_path_or_dir = (
                function_input["file_path"]
                if "file_path" in function_input
                else function_input["directory_path"]
            )
            valid_path = False
            output = ""
            if tool_call.function.name == "store_file_path":
                if function_path_or_dir in repo_context_manager.top_snippet_paths:
                    valid_path = (
                        function_path_or_dir in repo_context_manager.top_snippet_paths
                    )
                    output = f"SUCCESS. {function_path_or_dir} was stored."
                    paths_to_keep.append(function_path_or_dir)
                else: # we should add the file path
                    valid_path = repo_context_manager.is_path_valid(
                        function_path_or_dir, directory=False
                    )
                    highest_scoring_snippet = (
                        repo_context_manager.get_highest_scoring_snippet(
                            function_path_or_dir
                        )
                    )
                    new_file_contents = (
                        highest_scoring_snippet.xml
                        if highest_scoring_snippet is not None
                        else ""
                    )
                    repo_context_manager.add_file_paths([function_path_or_dir])
                    paths_to_add.append(function_path_or_dir)
                    output = (
                        f"SUCCESS: {function_path_or_dir} was added with contents {new_file_contents}."
                        if valid_path
                        else "FAILURE: This file path does not exist. Please try a new path."
                    )
            elif tool_call.function.name == "expand_directory":
                valid_path = repo_context_manager.is_path_valid(
                    function_path_or_dir, directory=True
                )
                repo_context_manager.expand_all_directories([function_path_or_dir])
                dir_string = str(repo_context_manager.dir_obj)
                output = (
                    f"SUCCESS: New repo_tree\n{dir_string}"
                    if valid_path
                    else "FAILURE: Invalid directory path."
                )
                if valid_path:
                    directories_to_expand.append(function_path_or_dir)
            tool_outputs.append(
                {
                    "tool_call_id": tool_call.id,
                    "output": output,
                }
            )
            justification = function_input["justification"] if "justification" in function_input else ""
            logger.info(
                f"Tool Call: {tool_call.function.name} {function_path_or_dir} {justification} Valid Tool Call: {valid_path}"
            )
        run = openai_retry_with_timeout(
            client.beta.threads.runs.submit_tool_outputs,
            thread_id=thread.id,
            run_id=run.id,
            tool_outputs=tool_outputs,
        )
    else:
        logger.warning(
            f"Context pruning iteration {iter} taking a long time. Breaking the loop. Status: {run.status}"
        )
    assistant_conversation = AssistantConversation.from_ids(
        assistant_id=run.assistant_id,
        run_id=run.id,
        thread_id=thread.id,
    )
    if assistant_conversation:
        ticket_progress.search_progress.pruning_conversation = assistant_conversation
    ticket_progress.save()
    logger.info(
        f"Context Management End:\npaths_to_keep: {paths_to_keep}\npaths_to_add: {paths_to_add}\ndirectories_to_expand: {directories_to_expand}"
    )
    if paths_to_keep or paths_to_add:
        repo_context_manager.remove_all_non_kept_paths(paths_to_keep + paths_to_add)
    if directories_to_expand:
        repo_context_manager.expand_all_directories(directories_to_expand)
    logger.info(
        f"Context Management End:\ncurrent snippet paths: {repo_context_manager.top_snippet_paths}"
    )
    paths_changed = set(initial_file_paths) != set(
        repo_context_manager.top_snippet_paths
    )
    # if the paths have not changed or all tools were empty, we are done
    return not (
        paths_changed and (paths_to_keep or directories_to_expand or paths_to_add)
    )


if __name__ == "__main__":
    import os

    from sweepai.utils.progress import TicketContext
    from sweepai.utils.ticket_utils import prep_snippets

    installation_id = os.environ["INSTALLATION_ID"]
    cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")
    query = "create a new search query filtering agent that will be used in ticket_utils.py. The agent should filter unnecessary terms out of the search query to be sent into lexical search. Use a prompt to do this, using name_agent.py as a reference."
    ticket_progress = TicketProgress(
        tracking_id="test",
    )
    import linecache
    import sys

    def trace_lines(frame, event, arg):
        if event == "line":
            filename = frame.f_code.co_filename
            if "context_pruning" in filename:
                lineno = frame.f_lineno
                line = linecache.getline(filename, lineno)
                print(f"Executing {filename}:line {lineno}:{line.rstrip()}")
        return trace_lines

    sys.settrace(trace_lines)
    repo_context_manager = prep_snippets(cloned_repo, query, ticket_progress)
    rcm = get_relevant_context(
        query,
        repo_context_manager,
        ticket_progress,
        chat_logger=ChatLogger({"username": "wwzeng1"}),
    )
    sys.settrace(None)
