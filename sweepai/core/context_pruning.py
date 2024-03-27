import json
import os
import re
import subprocess
import textwrap
import time
import urllib

import networkx as nx
import openai
from attr import dataclass
from loguru import logger
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.agents.assistant_function_modify import MAX_CHARS
from sweepai.agents.assistant_wrapper import openai_retry_with_timeout
from sweepai.config.server import DEFAULT_GPT4_32K_MODEL
from sweepai.core.entities import Snippet
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.openai_proxy import get_client
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.str_utils import FASTER_MODEL_MESSAGE
from sweepai.utils.modify_utils import post_process_rg_output
from sweepai.utils.tree_utils import DirectoryTree
from sweepai.config.client import SweepConfig

ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens

# 4. After you have stored a file snippet, use the keyword_search tool on any entities that appear but are not defined in the file snippet. For example, if the variable myUnit has type WorkUnit, you should keyword search for "WorkUnit" in order to find all filepaths where the keyword WorkUnit appears. You are then to iterate over the relevant filepaths to determine where the entities are defined. YOU MUST DO THIS. Once you have a list of relevant filepaths where the keyword is present, repeat the previous steps to determine if these filepaths should be added or dropped. Use the keyword_search tool to find the relevant files that the keyword shows up in. Repeat until you are certain that you have ALL relevant files you need.
# hypothesis tool, after each 1-3 do you have all info if it's missing a fn defn, you should use kw_search again
sys_prompt = """You are a brilliant engineer assigned to the following Github issue. You must gather ALL RELEVANT information from the codebase that allows you to completely solve the issue. It is very important that you get this right and do not miss any relevant lines of code.

## Instructions
You initially start with no snippets and must use the store_relevant_file_to_modify, store_relevant_file_to_read and expand_directory to add code snippets to the context. You must iteratively use the keyword_search, file_search and view_file tools to help you find the relevant snippets to store.

You are provided "Relevant Snippets", which are snippets relevant to the user request. These snippets are retrieved by a lexical search over the codebase, but are NOT in the context initially.

You will do this by using the following process for every relevant file:

1. First use the view_file tool to view all files that are relevant, starting with file paths and entities mentioned in "User Request", then those in "Relevant Snippets". 
For example, if the class foo.bar.Bar was mentioned, be sure to view foo/bar.py. If the file is irrelevant, move onto the next file. 
If you don't know the full file path, use file_search with the file name. Ensure you have checked ALL files referenced in the user request.
2. Now use the keyword_search tool on any variables, class and function calls that you do not have the definitions for. 
For example if the method foo(param1: typeX, param2: typeY) -> typeZ: is defined be sure to search for the keywords typeX, typeY and typeZ and find the files that contain their definitions.
This will return a list of file paths where the keyword shows up in. You MUST view the relevant files that the keyword shows up in.
3. When you have a relevant file, use the store_relevant_file_to_modify, store_relevant_file_to_read and expand_directory tools until you are completely sure about how to solve the user request. 
Continue repeating steps 1, 2, and 3 to get every file you need to solve the user request.
4. Finally, you can create a report and provide a plan to solve this code issue. Be sure to include enough detail as you will be passing this report onto an outside contractor who has zero prior knowledge of the code base or this issue. 
To do this use the submit_report_and_plan tool."""

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
        "name": "view_file",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File to view.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for viewing the file_path.",
                },
            },
            "required": ["file_path", "justification"],
        },
        "description": """Use this to view a file. You may use this tool multiple times. 
        After you are finished using this tool, you should use keyword_search on relevant entities inside the file in order to find their definitions. 
        You may use the store_relevant_file_to_modify or store_relevant_file_to_read tool to store the file to solve the user request.""",
    },
    {
        "name": "store_relevant_file_to_modify",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File or directory to store.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for why file_path is relevant and what functions we must change in this file.",
                },
            },
            "required": ["file_path", "justification"],
        },
        "description": """Use this to store a file that will be MODIFIED. Only store files you are CERTAIN are relevant to solving the user request.
        Once you have stored a file, use the keyword_search tool on any entities that you do not know the definition for in this file. This will search the entire codebase and allow you to find these definitions.""",
    },
    {
        "name": "store_relevant_file_to_read",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File or directory to store.",
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for why file_path is a relevant read only file and what functions we must read in this file.",
                },
            },
            "required": ["file_path", "justification"],
        },
        "description": """Use this to store a READ ONLY file. Only store paths you are CERTAIN are relevant and will help solve the user request, such as functions referenced in the modified files. 
        Once you have stored a file, use the keyword_search tool on any entities that you do not know the definition for in this file. This will search the entire codebase and allow you to find these definitions.""",
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
        "description": "Expand an existing directory that is closed. This is used for exploration and will not modify the stored files. If you expand a directory, you automatically expand all of its subdirectories, so do not list its subdirectories.",
    },
    {
        "name": "keyword_search",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": """Keyword to search for. This will search the entire code base for the keyword so make sure that the keyword you search for is descriptive. Avoid searching for generic words like: 'if' or 'else'.
If you are looking for a function call, search for it's respective language's definition like 'def foo(' in Python or 'function bar' in Javascript. """,
                },
                "justification": {
                    "type": "string",
                    "description": "Justification for why you are searching for this keyword and what it will provide. Example: I need to know the properties of this type in order to figure out what methods/properties are available for a certain variable.",
                },
            },
            "required": ["keyword", "justification"],
        },
        "description": """Use this to get a list of files with the corresponding lines of code where the keyword is present. 
        Use the view_file tool on each file to determine if they are relevant or not. Pay extra attention to definitions of classes, functions, and variable types.""",
    },
    {
        "name": "submit_report_and_plan",
        "parameters": {
            "type": "object",
            "properties": {
                "report": {
                    "type": "string",
                    "description": "Report of the issue. The report must contain enough information so that an outside contractor with no prior knowledge of the code base or issue can solve this problem.",
                },
                "plan": {
                    "type": "string",
                    "description": "High level plan on how to fix the issue.",
                },
            },
            "required": ["snippet_path", "justification"],
        },
        "description": """Use this tool to submit a report of the issue and a corresponding plan of how to fix it. The report should mention the root cause of the issue, what the intended behaviour should be and which files should be editted and which files should be read only. 
        The plan should provide a high level overview of what changes need to occur in each file as well as what look ups need to occur in each read only file.""",
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
    read_only_snippets: list[Snippet] = []
    issue_report_and_plan: str = ""
    import_trees: str = ""
    relevant_file_paths: list[
        str
    ] = []  # a list of file paths that appear in the user query

    @property
    def top_snippet_paths(self):
        return [snippet.file_path for snippet in self.current_top_snippets]
    
    @property
    def relevant_read_only_snippet_paths(self):
        return [snippet.file_path for snippet in self.read_only_snippets]

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
    
    def add_read_only_snippets(self, snippets_to_add: list[Snippet]):
        self.dir_obj.add_file_paths([snippet.file_path for snippet in snippets_to_add])
        for snippet in snippets_to_add:
            self.read_only_snippets.append(snippet)

    # does the same thing as add_snippets but adds it to the beginning of the list
    def boost_snippets_to_top(self, snippets_to_boost: list[Snippet]):
        self.dir_obj.add_file_paths([snippet.file_path for snippet in snippets_to_boost])
        for snippet in snippets_to_boost:
            self.current_top_snippets.insert(0, snippet)

    def add_import_trees(self, import_trees: str):
        self.import_trees += "\n" + import_trees

    def append_relevant_file_paths(self, relevant_file_paths: str):
        # do not use append, it modifies the list in place and will update it for ALL instances of RepoContextManager
        self.relevant_file_paths = self.relevant_file_paths + [relevant_file_paths]

    def set_relevant_paths(self, relevant_file_paths: list[str]):
        self.relevant_file_paths = relevant_file_paths
    
    def update_issue_report_and_plan(self, new_issue_report_and_plan: str):
        self.issue_report_and_plan = new_issue_report_and_plan


"""
Dump the import tree to a string
Ex:
main.py
├── database.py
│   └── models.py
└── utils.py
    └── models.py
"""


def build_full_hierarchy(
    graph: nx.DiGraph, start_node: str, k: int, prefix="", is_last=True, level=0
):
    if level > k:
        return ""
    if level == 0:
        hierarchy = f"{start_node}\n"
    else:
        hierarchy = f"{prefix}{'└── ' if is_last else '├── '}{start_node}\n"
    child_prefix = prefix + ("    " if is_last else "│   ")
    try:
        successors = {
            node
            for node, length in nx.single_source_shortest_path_length(
                graph, start_node, cutoff=1
            ).items()
            if length == 1
        }
    except Exception as e:
        print("error occured while fetching successors:", e)
        return hierarchy
    sorted_successors = sorted(successors)
    for idx, child in enumerate(sorted_successors):
        child_is_last = idx == len(sorted_successors) - 1
        hierarchy += build_full_hierarchy(
            graph, child, k, child_prefix, child_is_last, level + 1
        )
    if level == 0:
        try:
            predecessors = {
                node
                for node, length in nx.single_source_shortest_path_length(
                    graph.reverse(), start_node, cutoff=1
                ).items()
                if length == 1
            }
        except Exception as e:
            print("error occured while fetching predecessors:", e)
            return hierarchy
        sorted_predecessors = sorted(predecessors)
        for idx, parent in enumerate(sorted_predecessors):
            parent_is_last = idx == len(sorted_predecessors) - 1
            # Prepend parent hierarchy to the current node's hierarchy
            hierarchy = (
                build_full_hierarchy(graph, parent, k, "", parent_is_last, level + 1)
                + hierarchy
            )
    return hierarchy


def load_graph_from_file(filename):
    G = nx.DiGraph()
    current_node = None
    with open(filename, "r") as file:
        for line in file:
            if not line:
                continue
            if line.startswith(" "):
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
def build_import_trees(
    rcm: RepoContextManager, import_graph: nx.DiGraph, override_import_graph: nx.DiGraph = None
) -> tuple[RepoContextManager]:
    if import_graph is None and override_import_graph is None:
        return rcm
    if override_import_graph:
        import_graph = override_import_graph
    # if we have found relevant_file_paths in the query, we build their import trees
    code_files_in_query = rcm.relevant_file_paths
    if code_files_in_query:
        for file in code_files_in_query:
            # fetch direct parent and children
            representation = (
                f"\nThe file '{file}' has the following import structure: \n"
                + build_full_hierarchy(import_graph, file, 2)
            )
            rcm.add_import_trees(representation)
    # if there are no code_files_in_query, we build import trees for the top 5 snippets
    else:
        for snippet in rcm.current_top_snippets[:5]:
            file_path = snippet.file_path
            representation = (
                f"\nThe file '{file_path}' has the following import structure: \n"
                + build_full_hierarchy(import_graph, file_path, 2)
            )
            rcm.add_import_trees(representation)
    return rcm


# add any code files that appear in the query to current_top_snippets
def add_relevant_files_to_top_snippets(rcm: RepoContextManager) -> RepoContextManager:
    code_files_in_query = rcm.relevant_file_paths
    for file in code_files_in_query:
        current_top_snippet_paths = [
            snippet.file_path for snippet in rcm.current_top_snippets
        ]
        # if our mentioned code file isnt already in the current_top_snippets we add it
        if file not in current_top_snippet_paths:
            try:
                code_snippets = [
                    snippet for snippet in rcm.snippets if snippet.file_path == file
                ]
                rcm.boost_snippets_to_top(code_snippets)
            except Exception as e:
                logger.error(
                    f"Tried to add code file found in query but recieved error: {e}, skipping and continuing to next one."
                )
    return rcm


# fetch all files mentioned in the user query
def parse_query_for_files(
    query: str, rcm: RepoContextManager
) -> tuple[RepoContextManager, nx.DiGraph]:
    # use cloned_repo to attempt to find any files names that appear in the query
    repo_full_name = rcm.cloned_repo.repo_full_name
    repo_name = repo_full_name.split("/")[-1]
    repo_group_name = repo_full_name.split("/")[0]
    code_files_to_add = set([])
    code_files_to_check = set(list(rcm.cloned_repo.get_file_list()))
    code_files_uri_encoded = [
        urllib.parse.quote(file_path) for file_path in code_files_to_check
    ]
    # check if any code files are mentioned in the query
    for file, file_uri_encoded in zip(code_files_to_check, code_files_uri_encoded):
        if file in query or file_uri_encoded in query:
            code_files_to_add.add(file)
    for code_file in code_files_to_add:
        rcm.append_relevant_file_paths(code_file)
    # only for enterprise
    try:
        pathing = (
            f"{repo_group_name}_import_graphs/{repo_name}/{repo_name}_import_tree.txt"
        )
        if not os.path.exists(pathing):
            return rcm, None
        graph = load_graph_from_file(pathing)
    except Exception as e:
        logger.error(
            f"Error loading import tree: {e}, skipping step and setting import_tree to empty string"
        )
        return rcm, None
    files = set(list(graph.nodes()))
    files_uri_encoded = [urllib.parse.quote(file_path) for file_path in files]
    for file, file_uri_encoded in zip(files, files_uri_encoded):
        if (file in query or file_uri_encoded in query) and (
            file not in code_files_to_add
        ):
            rcm.append_relevant_file_paths(file)
    return rcm, graph


# do not ignore repo_context_manager
@file_cache(ignore_params=["ticket_progress", "chat_logger"])
def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    ticket_progress: TicketProgress | None = None,
    chat_logger: ChatLogger = None,
    override_import_graph: nx.DiGraph = None, # optional override import graph
):
    if chat_logger and chat_logger.use_faster_model():
        raise Exception(FASTER_MODEL_MESSAGE)
    model = DEFAULT_GPT4_32K_MODEL
    model, client = get_client()
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
        repo_context_manager, import_graph = parse_query_for_files(
            query, repo_context_manager
        )
        # for any code file mentioned in the query, build its import tree - This is currently not used
        repo_context_manager = build_import_trees(repo_context_manager, import_graph, override_import_graph=override_import_graph)
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
        wrapper = textwrap.TextWrapper(width=MAX_CHARS, replace_whitespace=False)
        messages = wrapper.wrap(user_prompt)
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
            if ticket_progress:
                discord_log_error(
                    f"Context manager empty ({ticket_progress.tracking_id})"
                )
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
    model: str = "gpt-4-0125-preview",
) -> bool | None:
    sweep_config = SweepConfig()
    max_iterations = 200
    directories_to_expand = []
    repo_context_manager.current_top_snippets = []
    initial_file_paths = repo_context_manager.top_snippet_paths
    paths_to_add = []
    num_tool_calls_made = 0
    model, client = get_client()
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
            current_read_only_snippets_string = "\n".join(
                [
                    "- " + snippet.xml
                    for snippet in repo_context_manager.read_only_snippets
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
            elif tool_call.function.name == "keyword_search":
                error_message = ""
                keyword = function_input["keyword"]
                rg_command = ["rg", "-n", "-i" , keyword, repo_context_manager.cloned_repo.repo_dir]
                try:
                    result = subprocess.run(rg_command, text=True, capture_output=True)
                    output = result.stdout
                    if output:
                        # post process rip grep output to be more condensed
                        rg_output_pretty = post_process_rg_output(repo_context_manager.cloned_repo.repo_dir, sweep_config, output)
                    else:
                        error_message = f"FAILURE: No results found for keyword: {keyword} in the entire codebase. Please try a new keyword. If you are searching for a function defintion try again with different whitespaces."
                except Exception as e:
                    logger.error(f"FAILURE: An Error occured while trying to find the keyword {keyword}: {e}")
                    error_message = f"FAILURE: An Error occured while trying to find the keyword {keyword}: {e}"
                if error_message:
                    output = error_message
                else:
                    output = (
                        f"SUCCESS: Here are the keyword_search results:\n\n{rg_output_pretty}"
                    )
                    
            elif tool_call.function.name == "view_file":
                error_message = ""
                # for key in ["start_line", "end_line"]:
                #     if key not in function_input:
                #         logger.warning(
                #             f"Key {key} not in function input {function_input}"
                #         )
                #         error_message = "FAILURE: Please provide a start and end line."
                # start_line = int(function_input["start_line"])
                # end_line = int(function_input["end_line"])
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
                # if start_line >= end_line:
                #     error_message = "FAILURE: Start line must be less than end line."
                if error_message:
                    output = error_message
                else:
                    # end_line = min(end_line, len(file_contents.splitlines()))
                    # logger.info(f"start_line: {start_line}, end_line: {end_line}")
                    # selected_file_contents = ""
                    # lines = file_contents.splitlines()
                    # expansion_width = 25
                    # start_index = max(0, start_line - expansion_width)
                    # for i, line in enumerate(lines[start_index:start_line]):
                    #     selected_file_contents += f"{i + start_index} | {line}\n"
                    # selected_file_contents += "\n===START OF SNIPPET===\n"
                    # for i, line in enumerate(lines[start_line:end_line]):
                    #     selected_file_contents += f"{i + start_line} | {line}\n"
                    # selected_file_contents += "\n===END OF SNIPPET===\n"
                    # for i, line in enumerate(
                    #     lines[end_line : end_line + expansion_width]
                    # ):
                    #     selected_file_contents += f"{i + end_line} | {line}\n"
                    output = (
                        f'Here are the contents of `{function_path_or_dir}:`\n```\n{file_contents}\n```\nIf you are CERTAIN this file is RELEVANT, call store_relevant_file_to_modify or store_relevant_file_to_read with the same parameters ({{"file_path": "{function_path_or_dir}"}}).'
                        if valid_path
                        else "FAILURE: This file path does not exist. Please try a new path."
                    )
            elif tool_call.function.name == "store_relevant_file_to_modify":
                error_message = ""
                # for key in ["start_line", "end_line"]:
                #     if key not in function_input:
                #         logger.warning(
                #             f"Key {key} not in function input {function_input}"
                #         )
                #         error_message = "FAILURE: Please provide a start and end line."
                # start_line = int(function_input["start_line"])
                # end_line = int(function_input["end_line"])
                # if end_line - start_line > 1000:
                #     error_message = (
                #         "FAILURE: Please provide a snippet of 1000 lines or less."
                #     )
                # if start_line >= end_line:
                #     error_message = "FAILURE: Start line must be less than end line."

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
                    # end_line = min(end_line, len(file_contents.splitlines()))
                    # logger.info(f"start_line: {start_line}, end_line: {end_line}")
                    snippet = Snippet(
                        file_path=function_path_or_dir,
                        start=0,
                        end=len(file_contents.splitlines()),
                        content=file_contents,
                    )
                    repo_context_manager.add_snippets([snippet])
                    paths_to_add.append(function_path_or_dir)
                    output = (
                        f"SUCCESS: {function_path_or_dir} was added with contents\n```\n{snippet.xml}\n```. Here are the current selected snippets that will be MODIFIED:\n{current_top_snippets_string}"
                        if valid_path
                        else "FAILURE: This file path does not exist. Please try a new path."
                    )
            elif tool_call.function.name == "store_relevant_file_to_read":
                error_message = ""
                # for key in ["start_line", "end_line"]:
                #     if key not in function_input:
                #         logger.warning(
                #             f"Key {key} not in function input {function_input}"
                #         )
                #         error_message = "FAILURE: Please provide a start and end line."
                # start_line = int(function_input["start_line"])
                # end_line = int(function_input["end_line"])
                # if end_line - start_line > 1000:
                #     error_message = (
                #         "FAILURE: Please provide a snippet of 1000 lines or less."
                #     )
                # if start_line >= end_line:
                #     error_message = "FAILURE: Start line must be less than end line."

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
                    # end_line = min(end_line, len(file_contents.splitlines()))
                    # logger.info(f"start_line: {start_line}, end_line: {end_line}")
                    snippet = Snippet(
                        file_path=function_path_or_dir,
                        start=0,
                        end=len(file_contents.splitlines()),
                        content=file_contents,
                    )
                    repo_context_manager.add_read_only_snippets([snippet])
                    paths_to_add.append(function_path_or_dir)
                    output = (
                        f"SUCCESS: {function_path_or_dir} was added with contents\n```\n{snippet.xml}\n```. Here are the current selected READ ONLY files:\n{current_read_only_snippets_string}"
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
            elif tool_call.function.name == "submit_report_and_plan":
                error_message = ""
                if "report" not in function_input or "plan" not in function_input:
                    error_message = "FAILURE: Please provide a report and a plan."
                issue_report = function_input["report"]
                issue_plan = function_input["plan"]
                repo_context_manager.update_issue_report_and_plan(f"#Report of Issue:\n\n{issue_report}\n\n#High Level Plan:\n\n{issue_plan}\n\n")
                if error_message:
                    output = error_message
                else:
                    output = "SUCCESS: Report and plan submitted."
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
        f"Context Management End:\ncurrent snippets to modify: {repo_context_manager.top_snippet_paths}\n current read only snippets: {repo_context_manager.relevant_read_only_snippet_paths}"
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
    try:
        import os

        from sweepai.utils.ticket_utils import prep_snippets
        from sweepai.utils.github_utils import get_installation_id
        organization_name = "sweepai"
        installation_id = get_installation_id(organization_name)
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
        # run with no chat_logger and ticket_progress
        repo_context_manager = prep_snippets(cloned_repo, query)
        rcm = get_relevant_context(
            query,
            repo_context_manager,
        )
    except Exception as e:
        logger.error(f"context_pruning.py failed to run successfully with error: {e}")
        raise e
