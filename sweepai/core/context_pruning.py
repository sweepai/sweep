import json
import re
import time

from attr import dataclass
from loguru import logger
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.agents.assistant_wrapper import client, openai_retry_with_timeout
from sweepai.core.entities import Snippet
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.tree_utils import DirectoryTree

ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens

sys_prompt = """You are a brilliant engineer assigned to the following Github issue. You must gather the information from the codebase that allows you to completely solve the issue. It is very important that you get this right.

Reply in the following format:

## Solution Planning
Use the snippets, user request, and repo_tree to determine the snippets that are critical to solve the issue.

1. First use the preview_file tool to preview any files that seem relevant. Then, use the view_file_snippet tool to view specific line numbers of a file. We want to find the exact line numbers to store to solve the user request. You may use this tool multiple times to view multiple snippets, either from the same file or different files.
2. Finally, use the store_file_snippet and expand_directory tools to optimize the context (snippets_in_repo and repo_tree) until they allow you to completely solve the user request. If you don't know the correct line numbers, complete step one until you find the exact line numbers.

Repeat this process until you have the perfect context to solve the user request."""

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
## User Request
{query}"""

functions = [
    {
        "name": "preview_file",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File path to preview.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for previewing the file.",
                },
            },
            "required": ["snippet_path", "justification"],
        },
        "description": "Use this to read the summary of the file. Use this tool before viewing a snippet. This is used for exploration only and does not affect the snippets. After using this tool, use the view_file_snippet tool to view specific line numbers of a file to find the exact line numbers to store to solve the user request.",
    },
    {
        "name": "view_file_snippet",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File or directory to store.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line of the snippet.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line of the snippet.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for viewing the file_path.",
                },
            },
            "required": ["file_path", "start_line", "end_line", "justification"],
        },
        "description": "Use this to view a section of a snippet. You may use this tool multiple times to view multiple snippets. After you are finished using this tool, you may use the store_file_snippet tool to store the snippet to solve the user request.",
    },
    {
        "name": "store_file_snippet",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File or directory to store.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line of the snippet.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line of the snippet. Pick the minimal required lines and prefer store multiple small and precise snippets over one large snippets.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for storing the file_path.",
                },
            },
            "required": ["file_path", "start_line", "end_line", "justification"],
        },
        "description": "Use this to store a snippet. Only store paths you are certain are relevant to solving the user request and be precise with the line numbers. Make sure to store ALL of the files that are referenced in the issue title or description.",
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
        "description": "Expand an existing directory that is closed. This is used for exploration only and does not affect the snippets. If you expand a directory, you automatically expand all of its subdirectories, so do not list its subdirectories. Store all files or directories that are referenced in the issue title or descriptions.",
    },
]

tools = [{"type": "function", "function": function} for function in functions]


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
    cloned_repo: ClonedRepo
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
        top_snippets_str = [
            f"<snippet file_path={snippet.file_path}>{snippet.get_snippet()}</snippet>"
            for snippet in self.current_top_snippets
        ]
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

    def add_snippets(self, snippets_to_add: list[Snippet]):
        self.dir_obj.add_file_paths([snippet.file_path for snippet in snippets_to_add])
        for snippet in snippets_to_add:
            self.current_top_snippets.append(snippet)


# @file_cache(ignore_params=["repo_context_manager", "ticket_progress", "chat_logger"])
def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    cloned_repo: ClonedRepo,
    ticket_progress: TicketProgress | None = None,
    chat_logger: ChatLogger = None,
):
    modify_iterations: int = 2
    model = (
        "gpt-3.5-turbo-1106"
        if (chat_logger and chat_logger.use_faster_model())
        else "gpt-4-1106-preview"
    )
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
        done = modify_context(
            thread, run, repo_context_manager, ticket_progress, cloned_repo=cloned_repo
        )
        return repo_context_manager
    except Exception as e:
        logger.exception(e)
        return repo_context_manager


def update_assistant_conversation(run: Run, thread: Thread):
    assistant_conversation = AssistantConversation.from_ids(
        assistant_id=run.assistant_id,
        run_id=run.id,
        thread_id=thread.id,
    )
    if ticket_progress:
        if assistant_conversation:
            ticket_progress.search_progress.pruning_conversation = (
                assistant_conversation
            )
        ticket_progress.search_progress.repo_tree = str(repo_context_manager.dir_obj)
        ticket_progress.search_progress.final_snippets = (
            repo_context_manager.current_top_snippets
        )
        ticket_progress.save()


def modify_context(
    thread: Thread,
    run: Run,
    repo_context_manager: RepoContextManager,
    ticket_progress: TicketProgress,
    cloned_repo: ClonedRepo,
) -> bool | None:
    max_iterations = 60
    directories_to_expand = []
    repo_context_manager.current_top_snippets = []
    initial_file_paths = repo_context_manager.top_snippet_paths
    paths_to_add = []
    for iter in range(max_iterations):
        run = openai_retry_with_timeout(
            client.beta.threads.runs.retrieve,
            thread_id=thread.id,
            run_id=run.id,
        )
        if iter % 5 == 0:
            update_assistant_conversation(run, thread)
            logger.info("iteration: " + str(iter))
        if run.status == "completed" or run.status == "failed":
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
            current_top_snippets_string = "\n".join(
                [
                    "- " + snippet.xml
                    for snippet in repo_context_manager.current_top_snippets
                ]
            )
            logger.info(f"Tool Call: {tool_call.function.name} {function_input}")
            function_path_or_dir = (
                function_input["file_path"]
                if "file_path" in function_input
                else function_input["directory_path"]
            )
            valid_path = False
            output = ""
            if tool_call.function.name == "view_file_snippet":
                error_message = ""
                for key in ["start_line", "end_line"]:
                    if key not in function_input:
                        logger.warning(
                            f"Key {key} not in function input {function_input}"
                        )
                        error_message = "FAILURE: Please provide a start and end line."
                start_line = int(function_input["start_line"])
                end_line = int(function_input["end_line"])
                logger.info(f"start_line: {start_line}, end_line: {end_line}")
                if error_message:
                    output = error_message
                else:
                    valid_path = repo_context_manager.is_path_valid(
                        function_path_or_dir, directory=False
                    )
                    file_contents = cloned_repo.get_file_contents(function_path_or_dir)
                    selected_file_contents = ""
                    lines = file_contents.splitlines()
                    expansion_width = 50
                    for i, line in enumerate(
                        lines[start_line - expansion_width : start_line]
                    ):
                        selected_file_contents += (
                            f"{i + start_line - expansion_width} | {line}\n"
                        )
                    selected_file_contents += "\n===START OF SNIPPET===\n"
                    for i, line in enumerate(lines[start_line:end_line]):
                        selected_file_contents += f"{i + start_line} | {line}\n"
                    selected_file_contents += "\n===END OF SNIPPET===\n"
                    for i, line in enumerate(
                        lines[end_line : end_line + expansion_width]
                    ):
                        selected_file_contents += f"{i + end_line} | {line}\n"
                    output = (
                        f"Here are the contents of `{function_path_or_dir}:{start_line}:{end_line}`\n```\n{selected_file_contents}\n```\If the above snippet contains all of the necessary contents to solve the user request BETWEEN the START and END tags, call store_file_snippet to store this snippet. Otherwise, call view_file_snippet again with a larger span."
                        if valid_path
                        else "FAILURE: This file path does not exist. Please try a new path."
                    )
            elif tool_call.function.name == "store_file_snippet":
                valid_path = (
                    function_path_or_dir in repo_context_manager.top_snippet_paths
                )
                error_message = ""
                for key in ["start_line", "end_line"]:
                    if key not in function_input:
                        logger.warning(
                            f"Key {key} not in function input {function_input}"
                        )
                        error_message = "FAILURE: Please provide a start and end line."
                start_line = int(function_input["start_line"])
                end_line = int(function_input["end_line"])
                logger.info(f"start_line: {start_line}, end_line: {end_line}")
                if end_line - start_line > 1000:
                    error_message = (
                        "FAILURE: Please provide a snippet of 1000 lines or less."
                    )

                try:
                    file_contents = cloned_repo.get_file_contents(function_path_or_dir)
                    valid_path = True
                except:
                    error_message = (
                        "FAILURE: This file path does not exist. Please try a new path."
                    )
                    valid_path = False
                if error_message:
                    output = error_message
                else:
                    snippet = Snippet(
                        file_path=function_path_or_dir,
                        start=start_line,
                        end=end_line,
                        content=file_contents,
                    )
                    repo_context_manager.add_snippets([snippet])
                    paths_to_add.append(function_path_or_dir)
                    output = (
                        f"SUCCESS: {function_path_or_dir} was added with contents\n```\n{snippet.xml}\n```. Here are the current selected snippets:\n{current_top_snippets_string}"
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
                    else "FAILURE: Invalid directory path. Please try a new path."
                )
                if valid_path:
                    directories_to_expand.append(function_path_or_dir)
            elif tool_call.function.name == "preview_file":
                valid_path = repo_context_manager.is_path_valid(
                    function_path_or_dir, directory=False
                )
                code = cloned_repo.get_file_contents(function_path_or_dir)
                file_preview = CodeTree.from_code(code).get_preview()
                output = (
                    f"SUCCESS: Previewing file {function_path_or_dir}:\n\n{file_preview}"
                    if valid_path
                    else "FAILURE: Invalid file path. Please try a new path."
                )
            logger.info(output)
            logger.info("Current top snippets:")
            for snippet in repo_context_manager.current_top_snippets:
                logger.info(snippet.denotation)
            logger.info("Paths to add:")
            for snippet in paths_to_add:
                logger.info(snippet)
            tool_outputs.append(
                {
                    "tool_call_id": tool_call.id,
                    "output": output,
                }
            )
            justification = (
                function_input["justification"]
                if "justification" in function_input
                else ""
            )
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
            f"Context pruning iteration taking too long. Status: {run.status}"
        )
    assistant_conversation = AssistantConversation.from_ids(
        assistant_id=run.assistant_id,
        run_id=run.id,
        thread_id=thread.id,
    )
    if ticket_progress:
        if assistant_conversation:
            ticket_progress.search_progress.pruning_conversation = (
                assistant_conversation
            )
        ticket_progress.save()
    logger.info(
        f"Context Management End:\npaths_to_add: {paths_to_add}\ndirectories_to_expand: {directories_to_expand}"
    )
    if directories_to_expand:
        repo_context_manager.expand_all_directories(directories_to_expand)
    logger.info(
        f"Context Management End:\ncurrent snippet paths: {repo_context_manager.top_snippet_paths}"
    )
    paths_changed = set(initial_file_paths) != set(
        repo_context_manager.top_snippet_paths
    )
    # if the paths have not changed or all tools were empty, we are done
    return not (paths_changed and (paths_to_add or directories_to_expand))


if __name__ == "__main__":
    import os

    from sweepai.utils.ticket_utils import prep_snippets

    installation_id = os.environ["INSTALLATION_ID"]
    cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")
    query = (
        "allow sweep.yaml to be read from the user/organization's .github repository"
    )
    # golden response is
    # sweepai/handlers/create_pr.py:401-428
    # sweepai/config/client.py:178-282
    ticket_progress = TicketProgress(
        tracking_id="test",
    )
    repo_context_manager = prep_snippets(cloned_repo, query, ticket_progress)
    rcm = get_relevant_context(
        query,
        repo_context_manager,
        ticket_progress,
        chat_logger=ChatLogger({"username": "wwzeng1"}),
    )
    for snippet in rcm.current_top_snippets:
        print(snippet.denotation)
