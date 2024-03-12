import json
import re
import textwrap
import time
import networkx as nx
import urllib
import os

import openai
from attr import dataclass
from loguru import logger
from openai import AzureOpenAI, OpenAI
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.agents.assistant_function_modify import MAX_CHARS
from sweepai.agents.assistant_wrapper import client, openai_retry_with_timeout
from sweepai.config.server import (
    AZURE_API_KEY,
    AZURE_OPENAI_DEPLOYMENT,
    DEFAULT_GPT4_32K_MODEL,
    IS_SELF_HOSTED,
    OPENAI_API_BASE,
    OPENAI_API_KEY,
    OPENAI_API_TYPE,
    OPENAI_API_VERSION,
)
from sweepai.core.entities import AssistantRaisedException, Snippet
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.tree_utils import DirectoryTree

if OPENAI_API_TYPE == "openai":
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=90) if OPENAI_API_KEY else None
elif OPENAI_API_TYPE == "azure":
    client = AzureOpenAI(
        azure_endpoint=OPENAI_API_BASE,
        api_key=AZURE_API_KEY,
        api_version=OPENAI_API_VERSION,
    )
    DEFAULT_GPT4_32K_MODEL = AZURE_OPENAI_DEPLOYMENT  # noqa: F811
else:
    raise Exception("OpenAI API type not set, must be either 'openai' or 'azure'.")


ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens

sys_prompt = """You are a brilliant engineer assigned to the following Github issue. You must gather ALL RELEVANT information from the codebase that allows you to completely solve the issue. It is very important that you get this right and do not miss any relevant lines of code.

## Instructions
You initially start with no snippets and will use the store_file_snippet and expand_directory to add snippets to the context. You will iteratively use the file_search, preview_file and view_file_snippet tools to help you find the relevant snippets to store.

You are provided "Relevant Snippets", which are snippets relevant to the user request. These snippets are retrieved by a lexical search over the codebase, but are NOT in the context initially.

You will do this by using the following process for every relevant file:

1. First use the preview_file tool to preview all files that are relevant, starting with file paths and entities mentioned in "User Request", then those in "Relevant Snippets". For example, if the class foo.bar.Bar was mentioned, be sure to preview foo/bar.py. If the file is irrelevant, move onto the next file. If you don't know the full file path, use file_search with the file name.
2. If the file seems relevant, use the view_file_snippet tool to view specific line numbers of a file. We want to find all line numbers relevant to solve the user request. So if the surrounding lines are relevant, use the view_file_snippet tool again with a larger span to view the surrounding lines. Repeat this process until you are certain you have the maximal relevant span.
3. Finally, when you are certain you have the maximal relevant span, use the store_file_snippet and expand_directory tools to curate the optimal context (snippets_in_repo and repo_tree) until they allow you to completely solve the user request. If you don't know the correct line numbers, complete step one until you find the exact line numbers.

Repeat this process until you have the perfect context to solve the user request. Ensure you have checked ALL files referenced in the user request."""

unformatted_user_prompt = """\
<repo_tree>
{repo_tree}
</repo_tree>

## Relevant Snippets
Here are potentially relevant snippets in the repo in decreasing relevance that you should use the preview_file tool for:
{snippets_in_repo}

## Code files mentioned in the user request
Here are the code files mentioned in the user request, these code files are very important to the solution and should be considered very relevant:
<code_files_in_query>
{file_paths_in_query}
</code_files_in_query>

## Import trees for code files in the user request
<import_trees>
{import_trees}
</import_trees>

## User Request
{query}"""

functions = [
    {
        "name": "file_search",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The search query. You can search like main.py to find src/main.py.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for searching for the file.",
                },
            },
            "required": ["snippet_path", "justification"],
        },
        "description": "Use this to find the most similar file paths to the search query.",
    },
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
        "description": "Use this to view a section of a snippet. You may use this tool multiple times to view multiple snippets. After you are finished using this tool, you may use the view_file_snippet to view the surrounding lines or the store_file_snippet tool to store the snippet to solve the user request.",
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
                    "description": "End line of the snippet.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for why file_path is relevant and why the surrounding lines are irrelevant by indicating what functions are in the surrounding lines and what they do.",
                },
            },
            "required": ["file_path", "start_line", "end_line", "justification"],
        },
        "description": "Use this to store a snippet. Only store paths you are CERTAIN are relevant and sufficient to solving the user request and be precise with the line numbers, and provides an entire coherent section of code. Make sure to store ALL of the files that are referenced in the issue title or description. You may store multiple snippets with the same file path.",
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
    import_trees: str = ""
    relevant_file_paths: list[str] = [] # a list of file paths that appear in the user query

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
            # if can_add_snippet(snippet, new_top_snippets):
            #     new_top_snippets.append(snippet)
            if True:
                new_top_snippets.append(snippet)
        self.current_top_snippets = new_top_snippets
        top_snippets_str = [
            f"- {snippet.denotation}" for snippet in self.current_top_snippets
        ]
        [snippet.file_path for snippet in self.current_top_snippets]
        snippets_in_repo_str = "\n".join(top_snippets_str)
        logger.info(f"Snippets in repo:\n{snippets_in_repo_str}")
        repo_tree = str(self.dir_obj)
        user_prompt = unformatted_user_prompt.format(
            query=query,
            snippets_in_repo=snippets_in_repo_str,
            repo_tree=repo_tree,
            import_trees=self.import_trees,
            file_paths_in_query=", ".join(self.relevant_file_paths),
        )
        return user_prompt

    def get_highest_scoring_snippet(self, file_path: str) -> Snippet:
        def snippet_key(snippet):
            return snippet.denotation

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
            key=lambda snippet: (
                self.snippet_scores[snippet_key(snippet)]
                if snippet_key(snippet) in self.snippet_scores
                else 0
            ),
        )
        return highest_scoring_snippet

    def add_snippets(self, snippets_to_add: list[Snippet]):
        self.dir_obj.add_file_paths([snippet.file_path for snippet in snippets_to_add])
        for snippet in snippets_to_add:
            self.current_top_snippets.append(snippet)

    def add_import_trees(self, import_trees: str):
        self.import_trees += ("\n" + import_trees)
    
    def append_relevant_file_paths(self, relevant_file_paths: str):
        # do not use append, it modifies the list in place and will update it for ALL instances of RepoContextManager
        self.relevant_file_paths = self.relevant_file_paths + [relevant_file_paths]

    def set_relevant_paths(self, relevant_file_paths: list[str]):
        self.relevant_file_paths = relevant_file_paths

"""
Dump the import tree to a string
Ex:
main.py
├── database.py
│   └── models.py
└── utils.py
    └── models.py
"""
def build_full_hierarchy(graph: nx.DiGraph, start_node: str, k:int, prefix='', is_last=True, level=0):
    if level > k:
        return ""
    if level == 0:
        hierarchy = f"{start_node}\n"
    else:
        hierarchy = f"{prefix}{'└── ' if is_last else '├── '}{start_node}\n"
    child_prefix = prefix + ("    " if is_last else "│   ")
    try:
        successors = {node for node, length in nx.single_source_shortest_path_length(graph, start_node, cutoff=1).items() if length == 1}
    except Exception as e:
        print("error occured while fetching successors:", e)
        return hierarchy
    sorted_successors = sorted(successors)
    for idx, child in enumerate(sorted_successors):
        child_is_last = idx == len(sorted_successors) - 1
        hierarchy += build_full_hierarchy(graph, child, k, child_prefix, child_is_last, level+1)
    if level == 0:
        try:
            predecessors = {node for node, length in nx.single_source_shortest_path_length(graph.reverse(), start_node, cutoff=1).items() if length == 1}
        except Exception as e:
            print("error occured while fetching predecessors:", e)
            return hierarchy
        sorted_predecessors = sorted(predecessors)
        for idx, parent in enumerate(sorted_predecessors):
            parent_is_last = idx == len(sorted_predecessors) - 1
            # Prepend parent hierarchy to the current node's hierarchy
            hierarchy = build_full_hierarchy(graph, parent, k, '', parent_is_last, level+1) + hierarchy
    return hierarchy

def load_graph_from_file(filename):
    G = nx.DiGraph()
    current_node = None
    with open(filename, 'r') as file:
        for line in file:
            if not line: 
                continue
            if line.startswith(' '):
                line = line.strip()
                if current_node:
                    G.add_edge(current_node, line)
            else:
                line = line.strip()
                current_node = line
                if current_node:
                    G.add_node(current_node)
    return G

# add import trees for any relevant_file_paths (code files that appear in query)
def build_import_trees(rcm: RepoContextManager, import_graph: nx.DiGraph) -> tuple[RepoContextManager]:
    if import_graph is None:
        return rcm
    code_files_in_query = rcm.relevant_file_paths
    for file in code_files_in_query:
        # fetch direct parent and children
        representation = f"\nThe file '{file}' has the following import structure: \n" + build_full_hierarchy(import_graph, file, 2)
        rcm.add_import_trees(representation)
    return rcm

# add any code files that appear in the query to current_top_snippets
def add_relevant_files_to_top_snippets(rcm: RepoContextManager) -> RepoContextManager:
    code_files_in_query = rcm.relevant_file_paths
    for file in code_files_in_query:
        current_top_snippet_paths = [snippet.file_path for snippet in rcm.current_top_snippets]
        # if our mentioned code file isnt already in the current_top_snippets we add it
        if file not in current_top_snippet_paths:
            try:
                code_snippets = [snippet for snippet in rcm.snippets if snippet.file_path == file]
                rcm.add_snippets(code_snippets)
            except Exception as e:
                logger.error(f"Tried to add code file found in query but recieved error: {e}, skipping and continuing to next one.")
    return rcm

# fetch all files mentioned in the user query
def parse_query_for_files(query: str, rcm: RepoContextManager) -> tuple[RepoContextManager, nx.DiGraph]:
    # use cloned_repo to attempt to find any files names that appear in the query
    repo_full_name = rcm.cloned_repo.repo_full_name
    repo_name = repo_full_name.split("/")[-1]
    repo_group_name = repo_full_name.split("/")[0]
    code_files_to_add = set([])
    code_files_to_check = set(list(rcm.cloned_repo.get_file_list()))
    code_files_uri_encoded = [urllib.parse.quote(file_path) for file_path in code_files_to_check]
    for file, file_uri_encoded in zip(code_files_to_check, code_files_uri_encoded):
        if file in query or file_uri_encoded in query:
            code_files_to_add.add(file)
    for code_file in code_files_to_add:
        rcm.append_relevant_file_paths(code_file)
    # only for enterprise
    try:
        pathing = f"{repo_group_name}_import_graphs/{repo_name}/{repo_name}_import_tree.txt"
        if not os.path.exists(pathing):
            return rcm, None
        graph = load_graph_from_file(pathing)
    except Exception as e:
        logger.error(f"Error loading import tree: {e}, skipping step and setting import_tree to empty string")
        return rcm, None
    files = set(list(graph.nodes()))
    files_uri_encoded = [urllib.parse.quote(file_path) for file_path in files]
    for file, file_uri_encoded in zip(files, files_uri_encoded):
        if (file in query or file_uri_encoded in query) and (file not in code_files_to_add):
            rcm.append_relevant_file_paths(file)
    return rcm, graph
    
# do not ignore repo_context_manager
@file_cache(ignore_params=["ticket_progress", "chat_logger"])
def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    ticket_progress: TicketProgress | None = None,
    chat_logger: ChatLogger = None,
):
    model = (
        "gpt-3.5-turbo-1106"
        if (chat_logger is None or chat_logger.use_faster_model())
        and not IS_SELF_HOSTED
        else DEFAULT_GPT4_32K_MODEL
    )
    posthog.capture(
        chat_logger.data.get("username") if chat_logger is not None else "anonymous",
        "call_assistant_api",
        {
            "query": query,
            "model": model,
        },
    )
    try:
        # attempt to get import tree for relevant snippets that show up in the query
        repo_context_manager, import_graph = parse_query_for_files(query, repo_context_manager)
        # for any code file mentioned in the query, build its import tree
        repo_context_manager = build_import_trees(repo_context_manager, import_graph)
        # for any code file mentioned in the query add it to the top relevant snippets
        repo_context_manager = add_relevant_files_to_top_snippets(repo_context_manager)
        # check to see if there are any files that are mentioned in the query
        user_prompt = repo_context_manager.format_context(
            unformatted_user_prompt=unformatted_user_prompt,
            query=query,
        )
        messages = textwrap.wrap(user_prompt, MAX_CHARS)
        assistant = openai_retry_with_timeout(
            client.beta.assistants.create,
            name="Relevant Files Assistant",
            instructions=sys_prompt,
            tools=tools,
            model=model,
        )
        thread = openai_retry_with_timeout(client.beta.threads.create)
        for content in messages:
            _ = openai_retry_with_timeout(
                client.beta.threads.messages.create,
                thread.id,
                role="user",
                content=content,
            )
        run = openai_retry_with_timeout(
            client.beta.threads.runs.create,
            thread_id=thread.id,
            assistant_id=assistant.id,
        )
        old_top_snippets = [
            snippet for snippet in repo_context_manager.current_top_snippets
        ]
        try:
            modify_context(
                thread, run, repo_context_manager, ticket_progress, model=model
            )
        except openai.BadRequestError as e:  # sometimes means that run has expired
            logger.exception(e)
        if len(repo_context_manager.current_top_snippets) == 0:
            repo_context_manager.current_top_snippets = old_top_snippets
            discord_log_error(f"Context manager empty ({ticket_progress.tracking_id})")
        return repo_context_manager
    except Exception as e:
        logger.exception(e)
        return repo_context_manager


def update_assistant_conversation(
    run: Run,
    thread: Thread,
    ticket_progress: TicketProgress,
    repo_context_manager: RepoContextManager,
):
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
    model: str = "gpt-4-1106-preview",
) -> bool | None:
    max_iterations = 200
    directories_to_expand = []
    repo_context_manager.current_top_snippets = []
    initial_file_paths = repo_context_manager.top_snippet_paths
    paths_to_add = []
    num_tool_calls_made = 0
    for iter in range(max_iterations):
        run = openai_retry_with_timeout(
            client.beta.threads.runs.retrieve,
            thread_id=thread.id,
            run_id=run.id,
        )
        if iter % 5 == 0:
            update_assistant_conversation(
                run, thread, ticket_progress, repo_context_manager
            )
            logger.info("iteration: " + str(iter) + f" run status {run.status}")
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
        num_tool_calls_made += 1
        if num_tool_calls_made > 15 and model.startswith("gpt-3.5"):
            raise AssistantRaisedException("Too many tool calls made on gpt-3.5.")
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []
        for tool_call in tool_calls:
            try:
                tool_call_arguments = re.sub(r"\\+'", "", tool_call.function.arguments)
                function_input = json.loads(tool_call_arguments)
            except Exception:
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
            function_path_or_dir = function_input.get(
                "file_path"
            ) or function_input.get("directory_path")
            valid_path = False
            output = ""
            if tool_call.function.name == "file_search":
                error_message = ""
                try:
                    similar_file_paths = "\n".join(
                        [
                            f"- {path}"
                            for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                                function_path_or_dir
                            )
                        ]
                    )
                    valid_path = True
                except Exception:
                    similar_file_paths = ""
                    error_message = "FAILURE: This file path does not exist."
                if error_message:
                    output = error_message
                else:
                    output = (
                        f"SUCCESS: Here are the most similar file paths to {function_path_or_dir}:\n{similar_file_paths}"
                        if valid_path
                        else "FAILURE: This file path does not exist. Please try a new path."
                    )
            elif tool_call.function.name == "view_file_snippet":
                error_message = ""
                for key in ["start_line", "end_line"]:
                    if key not in function_input:
                        logger.warning(
                            f"Key {key} not in function input {function_input}"
                        )
                        error_message = "FAILURE: Please provide a start and end line."
                start_line = int(function_input["start_line"])
                end_line = int(function_input["end_line"])
                try:
                    file_contents = repo_context_manager.cloned_repo.get_file_contents(
                        function_path_or_dir
                    )
                    valid_path = True
                except Exception:
                    file_contents = ""
                    similar_file_paths = "\n".join(
                        [
                            f"- {path}"
                            for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                                function_path_or_dir
                            )
                        ]
                    )
                    error_message = f"FAILURE: This file path does not exist. Did you mean:\n{similar_file_paths}"
                if start_line >= end_line:
                    error_message = "FAILURE: Start line must be less than end line."
                if error_message:
                    output = error_message
                else:
                    end_line = min(end_line, len(file_contents.splitlines()))
                    logger.info(f"start_line: {start_line}, end_line: {end_line}")
                    selected_file_contents = ""
                    lines = file_contents.splitlines()
                    expansion_width = 25
                    start_index = max(0, start_line - expansion_width)
                    for i, line in enumerate(lines[start_index:start_line]):
                        selected_file_contents += f"{i + start_index} | {line}\n"
                    selected_file_contents += "\n===START OF SNIPPET===\n"
                    for i, line in enumerate(lines[start_line:end_line]):
                        selected_file_contents += f"{i + start_line} | {line}\n"
                    selected_file_contents += "\n===END OF SNIPPET===\n"
                    for i, line in enumerate(
                        lines[end_line : end_line + expansion_width]
                    ):
                        selected_file_contents += f"{i + end_line} | {line}\n"
                    output = (
                        f'Here are the contents of `{function_path_or_dir}:{start_line}:{end_line}`\n```\n{selected_file_contents}\n```\nCheck if there is additional relevant context surrounding the snippet BETWEEN the START and END tags necessary to solve the user request. If so, call view_file_snippet again with a larger span. If you are CERTAIN this snippet is COMPLETELY SUFFICIENT and RELEVANT, and no surrounding lines provide ANY additional relevant context, call store_file_snippet with the same parameters ({{"file_path": "{function_path_or_dir}", "start_line": "{start_line}", "end_line": "{end_line}"}}).'
                        if valid_path
                        else "FAILURE: This file path does not exist. Please try a new path."
                    )
            elif tool_call.function.name == "store_file_snippet":
                error_message = ""
                for key in ["start_line", "end_line"]:
                    if key not in function_input:
                        logger.warning(
                            f"Key {key} not in function input {function_input}"
                        )
                        error_message = "FAILURE: Please provide a start and end line."
                start_line = int(function_input["start_line"])
                end_line = int(function_input["end_line"])
                if end_line - start_line > 1000:
                    error_message = (
                        "FAILURE: Please provide a snippet of 1000 lines or less."
                    )
                if start_line >= end_line:
                    error_message = "FAILURE: Start line must be less than end line."

                try:
                    file_contents = repo_context_manager.cloned_repo.get_file_contents(
                        function_path_or_dir
                    )
                    valid_path = True
                except Exception:
                    file_contents = ""
                    similar_file_paths = "\n".join(
                        [
                            f"- {path}"
                            for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                                function_path_or_dir
                            )
                        ]
                    )
                    error_message = f"FAILURE: This file path does not exist. Did you mean:\n{similar_file_paths}"
                if error_message:
                    output = error_message
                else:
                    end_line = min(end_line, len(file_contents.splitlines()))
                    logger.info(f"start_line: {start_line}, end_line: {end_line}")
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
                error_message = ""
                try:
                    code = repo_context_manager.cloned_repo.get_file_contents(
                        function_path_or_dir
                    )
                    valid_path = True
                except Exception:
                    code = ""
                    similar_file_paths = "\n".join(
                        [
                            f"- {path}"
                            for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                                function_path_or_dir
                            )
                        ]
                    )
                    error_message = f"FAILURE: This file path does not exist. Did you mean:\n{similar_file_paths}"
                if error_message:
                    output = error_message
                else:
                    file_preview = CodeTree.from_code(code).get_preview()
                    output = f"SUCCESS: Previewing file {function_path_or_dir}:\n\n{file_preview}"
            else:
                output = f"FAILURE: Invalid tool name {tool_call.function.name}"
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
    repo_context_manager.current_top_snippets = [
        snippet
        for snippet in repo_context_manager.current_top_snippets
        if snippet.file_path != "sweep.yaml"
    ]
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
