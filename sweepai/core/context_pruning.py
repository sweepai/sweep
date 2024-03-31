from copy import deepcopy
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
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.core.reflection_utils import EvaluatorAgent
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.convert_openai_anthropic import MockFunctionCall
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.modify_utils import post_process_rg_output
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.tree_utils import DirectoryTree

ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens
NUM_SNIPPETS_TO_SHOW_AT_START = 15

# TODO:
# - Add self-evaluation / chain-of-verification

anthropic_function_calls = """<tool_description>
<tool_name>view_file</tool_name>
<description>
Retrieves the contents of the specified file. After viewing a file, use `code_search` on relevant entities to find their definitions. Use `store_file` to add the file to the context if it's relevant to solving the issue.
</description>
<parameters>
<parameter>
<name>file_path</name>
<type>string</type>
<description>The path of the file to view.</description>
</parameter>
<parameter>
<name>justification</name>
<type>string</type>
<description>Explain why viewing this file is necessary to solve the issue.</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>store_file</tool_name>
<description>
Adds a file to the context that needs to be modified or used to resolve the issue. Provide a code excerpt in the justification showcasing the file's relevance, i.e. how it should be fixed or another part of the codebase that is relevant and uses this module. After using this tool, use `code_search` to find definitions of unknown functions /classes in the file to add to files to use.
</description>
<parameters>
<parameter>
<name>file_path</name>
<type>string</type>
<description>The path of the file to store.</description>
</parameter>
<parameter>
<name>justification</name>
<type>string</type>
<description>Explain why this file should be modified or read and what needs to be modified. Include a supporting code excerpt.</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>code_search</tool_name>
<description>
Searches the entire codebase for the given code_entity and returns a list of files and line numbers where it appears. Use this to find definitions of unknown types, classes and functions. Review the search results using `view_file` to determine relevance. Focus on definitions.
</description>
<parameters>
<parameter>
<name>code_entity</name>
<type>string</type>
<description>The code_entity to search for. Should be a distinctive name, not a generic term like 'if' or 'else'. For functions, search for the definition syntax, e.g. 'def foo(' in Python or 'function bar' in JavaScript.</description>
</parameter>
<parameter>
<name>justification</name>
<type>string</type>
<description>Explain what information you expect to get from this search and why it's needed, e.g. "I need to find the definition of the Foo class to see what methods are available on Foo objects."</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>submit_report_and_plan</tool_name>
<description>
Provides a detailed report of the issue and a high-level plan to resolve it. The report should explain the root cause, expected behavior, and which files need to be modified or referenced. The plan should outline the changes needed in each file. Write it for an outside contractor with no prior knowledge of the codebase or issue. You may only call this tool once when you are absolutely certain you have all the necessary information.
</description>
<parameters>
<parameter>
<name>report</name>
<type>string</type>
<description>A detailed report providing background information and explaining the issue so that someone with no context can understand it.</description>
</parameter>
<parameter>
<name>plan</name>
<type>string</type>
<description>A high-level plan outlining the steps to resolve the issue, including what needs to be modified in each file to modify and file to use.</description>
</parameter>
</parameters>
</tool_description>

You must call one tool at a time using the specified XML format. Here are some generic examples to illustrate the format without referring to a specific task:

Example 1:
<function_call>
<invoke>
<tool_name>view_file</tool_name>
<parameters>
<file_path>src/controllers/user_controller.py</file_path>
<justification>I found the user_controller.py file in the previous search. I now need to view its contents to understand the UserController class implementation and determine if it needs to be modified to resolve the issue.</justification>
</parameters>
</invoke>
</function_call>

Example 2:
<function_call>
<tool_name>store_file</tool_name>
<invoke>
<parameters>
<file_path>src/controllers/user_controller.py</file_path>
<justification>The user_controller.py file contains the UserController class referenced in the user request. The create_user method inside this class needs to be updated to fix the bug, as evidenced by this excerpt:
```python
def create_user(self, name, email):
    # BUG: User is created without validating email
    user = User(name, email)
    db.session.add(user)
    db.session.commit()
```
</justification>
</parameters>
</invoke>
</function_call>

Example 3:
<function_call>
<invoke>
<tool_name>code_search</tool_name>
<parameters>
<code_entity>class User(db.Model):</code_entity>
<justification>The user_controller.py file references the User class, but I don't see its definition in this file. I need to search for 'class User(db.Model):' to find where the User model is defined, as this will provide necessary context about the User class to properly fix the create_user bug.</justification>
</parameters>
</invoke>
</function_call>

I will provide the tool's response after each call, then you may call another tool as you work towards a solution. Focus on the actual issue at hand rather than these illustrative examples."""

sys_prompt = """You are a brilliant engineer assigned to solve the following GitHub issue. Your task is to retrieve relevant files to resolve the GitHub issue. We consider a file RELEVANT if it must either be modified or used as part of the issue resolution process. It is critical that you identify and include every relevant line of code that should either be modified or used.

You will gather all of the relevant file paths.

## Instructions
- You start with no code snippets. Use the store_file tool to incrementally add relevant code to the context.
- Utilize the code_search and view_file tools to methodically find the code snippets you need to store.
- "Relevant Snippets" provides code snippets that may be relevant to the issue. However, these are not automatically added to the context.

Use the following iterative process:
1. View all files that seem relevant based on file paths and entities mentioned in the "User Request" and "Relevant Snippets". For example, if the class foo.bar.Bar is referenced, be sure to view foo/bar.py. Skip irrelevant files.
2. Use code_search to find definitions for any unknown variables, classes, and functions. For instance, if the method foo(param1: typeX, param2: typeY) -> typeZ is used, search for the keywords typeX, typeY, and typeZ to find where they are defined. View the relevant files containing those definitions.
3. When you identify a relevant file, use store_file to add it to the context.
Repeat steps 1-3 until you are confident you have all the necessary code to resolve the issue.
4. Lastly, generate a detailed plan of attack explaining the issue and outlining a plan to resolve it. List each file that should be modified, what should be modified about it, and which modules we need to use. Write in extreme detail, since it is for an intern who is new to the codebase and project. Use the submit_report_and_plan tool for this.

Here are the tools at your disposal. Call them one at a time as needed until you have gathered all relevant information:

""" + anthropic_function_calls

unformatted_user_prompt = """\
## Relevant Snippets
Here are potentially relevant snippets in the repo in decreasing relevance that you should use the `view_file` tool to review:
{snippets_in_repo}

## Code files mentioned in the user request
Here are the code files mentioned in the user request, these code files are very important to the solution and should be considered very relevant:
<code_files_in_query>
{file_paths_in_query}
</code_files_in_query>
{import_tree_prompt}
## User Request
<user_request>
{query}
<user_request>"""

PLAN_SUBMITTED_MESSAGE = "SUCCESS: Report and plan submitted."


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
    current_top_snippets: list[Snippet] = field(default_factory=list)
    read_only_snippets: list[Snippet] = field(default_factory=list)
    issue_report_and_plan: str = ""
    import_trees: str = ""
    relevant_file_paths: list[str] = field(
        default_factory=list
    )  # a list of file paths that appear in the user query

    @property
    def top_snippet_paths(self):
        return [snippet.file_path for snippet in self.current_top_snippets]

    @property
    def relevant_read_only_snippet_paths(self):
        return [snippet.file_path for snippet in self.read_only_snippets]

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
        top_snippets_str = [snippet.file_path for snippet in self.current_top_snippets]
        # dedupe the list inplace
        top_snippets_str = list(dict.fromkeys(top_snippets_str))
        top_snippets_str = top_snippets_str[:NUM_SNIPPETS_TO_SHOW_AT_START]
        snippets_in_repo_str = "\n".join(top_snippets_str)
        logger.info(f"Snippets in repo:\n{snippets_in_repo_str}")
        repo_tree = str(self.dir_obj)
        import_tree_prompt = """
## Import trees for code files in the user request
<import_trees>
{import_trees}
</import_trees>
"""
        import_tree_prompt = (
            import_tree_prompt.format(import_trees=self.import_trees)
            if self.import_trees
            else ""
        )
        user_prompt = unformatted_user_prompt.format(
            query=query,
            snippets_in_repo=snippets_in_repo_str,
            repo_tree=repo_tree,
            import_tree_prompt=import_tree_prompt,
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
        # self.dir_obj.add_file_paths([snippet.file_path for snippet in snippets_to_add])
        for snippet in snippets_to_add:
            self.current_top_snippets.append(snippet)

    # does the same thing as add_snippets but adds it to the beginning of the list
    def boost_snippets_to_top(self, snippets_to_boost: list[Snippet]):
        # self.dir_obj.add_file_paths([snippet.file_path for snippet in snippets_to_boost])
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
    rcm: RepoContextManager,
    import_graph: nx.DiGraph,
    override_import_graph: nx.DiGraph = None,
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
# @file_cache(ignore_params=["ticket_progress", "chat_logger"])
def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    seed: int = None,
    ticket_progress: TicketProgress = None,
    chat_logger: ChatLogger = None,
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
            repo_context_manager = context_dfs(
                user_prompt,
                repo_context_manager,
                problem_statement=query,
            )
        except openai.BadRequestError as e:  # sometimes means that run has expired
            logger.exception(e)
        if len(repo_context_manager.current_top_snippets) == 0:
            repo_context_manager.current_top_snippets = old_top_snippets
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


CLAUDE_MODEL = "claude-3-haiku-20240307"


def validate_and_parse_function_calls(
    function_calls_string: str, chat_gpt: ChatGPT
) -> list[MockFunctionCall]:
    function_calls = MockFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</function_call>"
    )  # add end tag
    if len(function_calls) > 0:
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</function_call>"
        )  # add end tag to assistant message
        return function_calls

    # try adding </invoke> tag as well
    function_calls = MockFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</invoke>\n</function_call>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</invoke>\n</function_call>"
        )
        return function_calls
    # try adding </parameters> tag as well
    function_calls = MockFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n")
        + "\n</parameters>\n</invoke>\n</function_call>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n")
            + "\n</parameters>\n</invoke>\n</function_call>"
        )
    return function_calls


def handle_function_call(
    repo_context_manager: RepoContextManager, function_call: MockFunctionCall
):
    function_name = function_call.function_name
    function_input = function_call.function_parameters
    logger.info(f"Tool Call: {function_name} {function_input}")
    file_path = function_input.get("file_path")
    valid_path = False
    output_prefix = f"Output for {function_name}:\n"
    output = ""
    current_read_only_snippets_string = "\n".join(
        [snippet.denotation for snippet in repo_context_manager.read_only_snippets]
    )
    current_top_snippets_string = "\n".join(
        [snippet.denotation for snippet in repo_context_manager.current_top_snippets]
    )
    if function_name == "code_search":
        code_entity = f'"{function_input["code_entity"]}"'  # handles cases with two words
        rg_command = [
            "rg",
            "-n",
            "-i",
            code_entity,
            repo_context_manager.cloned_repo.repo_dir,
        ]
        try:
            result = subprocess.run(
                " ".join(rg_command), text=True, shell=True, capture_output=True
            )
            rg_output = result.stdout
            if rg_output:
                # post process rip grep output to be more condensed
                rg_output_pretty = post_process_rg_output(
                    repo_context_manager.cloned_repo.repo_dir, SweepConfig(), rg_output
                )
                output = (
                    f"SUCCESS: Here are the code_search results:\n\n{rg_output_pretty}"
                )
            else:
                output = f"FAILURE: No results found for code_entity: {code_entity} in the entire codebase. Please try a new code_entity. If you are searching for a function defintion try again with different whitespaces."
        except Exception as e:
            logger.error(
                f"FAILURE: An Error occured while trying to find the code_entity {code_entity}: {e}"
            )
            output = f"FAILURE: An Error occured while trying to find the code_entity {code_entity}: {e}"
    elif function_name == "view_file":
        try:
            file_contents = repo_context_manager.cloned_repo.get_file_contents(
                file_path
            )
            valid_path = True
            if (
                file_path in current_read_only_snippets_string
                and file_path in current_top_snippets_string
                and valid_path
            ):
                output = f"FAILURE: {file_path} is already in the selected snippets."
            elif valid_path:
                suffix = f'\nIf you are CERTAIN this file is RELEVANT, call store_file with the same parameters ({{"file_path": "{file_path}"}}).'
                output = f'Here are the contents of `{file_path}:`\n```\n{file_contents}\n```'
                if snippet.denotation not in current_top_snippets_string:
                    output += suffix
            else:
                output = (
                    "FAILURE: This file path does not exist. Please try a new path."
                )
        except Exception:
            file_contents = ""
            similar_file_paths = "\n".join(
                [
                    f"- {path}"
                    for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                        file_path
                    )
                ]
            )
            output = f"FAILURE: This file path does not exist. Did you mean:\n{similar_file_paths}"
    elif function_name == "store_file":
        try:
            file_contents = repo_context_manager.cloned_repo.get_file_contents(
                file_path
            )
            valid_path = True
        except Exception:
            file_contents = ""
            similar_file_paths = "\n".join(
                [
                    f"- {path}"
                    for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                        file_path
                    )
                ]
            )
            output = f"FAILURE: This file path does not exist. Did you mean:\n{similar_file_paths}"
        else:
            snippet = Snippet(
                file_path=file_path,
                start=0,
                end=len(file_contents.splitlines()),
                content=file_contents,
            )
            if snippet.denotation in current_top_snippets_string:
                output = f"FAILURE: {file_path} is already in the selected snippets."
            else:
                repo_context_manager.add_snippets([snippet])
                current_top_snippets_string = "\n".join(
                    [
                        snippet.denotation
                        for snippet in repo_context_manager.current_top_snippets
                    ]
                )
                output = (
                    f"SUCCESS: {file_path} was added. Here are the current selected snippets that will either be modified or use in the code change:\n{current_top_snippets_string}"
                    if valid_path
                    else "FAILURE: This file path does not exist. Please try a new path."
                )
    elif function_name == "preview_file":
        try:
            code = repo_context_manager.cloned_repo.get_file_contents(file_path)
            valid_path = True
        except Exception:
            code = ""
            similar_file_paths = "\n".join(
                [
                    f"- {path}"
                    for path in repo_context_manager.cloned_repo.get_similar_file_paths(
                        file_path
                    )
                ]
            )
            output = f"FAILURE: This file path does not exist. Did you mean:\n{similar_file_paths}"
        else:
            file_preview = CodeTree.from_code(code).get_preview()
            output = f"SUCCESS: Previewing file {file_path}:\n\n{file_preview}"
    elif function_name == "submit_report_and_plan":
        if "report" not in function_input or "plan" not in function_input:
            output = "FAILURE: Please provide a report and a plan."
        else:
            issue_report = function_input["report"]
            issue_plan = function_input["plan"]
            repo_context_manager.update_issue_report_and_plan(
                f"#Report of Issue:\n\n{issue_report}\n\n#High Level Plan:\n\n{issue_plan}\n\n"
            )
            output = PLAN_SUBMITTED_MESSAGE
    else:
        output = f"FAILURE: Invalid tool name {function_name}"
    justification = (
        function_input["justification"] if "justification" in function_input else ""
    )
    logger.info(
        f"Tool Call: {function_name} {justification} Valid Tool Call: {valid_path}"
    )
    return output_prefix + output


reflections_prompt_prefix = """
CRITICAL FEEDBACK - READ CAREFULLY AND ADDRESS ALL POINTS
<critical_feedback_to_address>
Here is the feedback from your previous attempt. You MUST read this extremely carefully and follow ALL of the reviewer's advice. If they tell you to store specific files, store and view all of those first. If you do not fully address this feedback you will fail to retrieve all of the relevant files.
{all_reflections}
</critical_feedback_to_address>"""

reflection_prompt = """<attempt_and_feedback_{idx}>
<previous_files_stored>
Files stored from previous attempt:
{files_read}
</previous_files_stored>
<feedback>
Reviewer feedback on previous attempt:
{reflections_string}
</feedback>
</attempt_and_feedback_{idx}>"""


def context_dfs(
    user_prompt: str,
    repo_context_manager: RepoContextManager,
    problem_statement: str,
) -> bool | None:
    max_iterations = 30 # Tuned to 30 because haiku is cheap
    NUM_ROLLOUTS = 5
    repo_context_manager.current_top_snippets = []
    # initial function call
    reflections_to_read_files = {}
    rollouts_to_scores_and_rcms = {}
    def perform_rollout(repo_context_manager: RepoContextManager, reflections_to_gathered_files: dict[str, list[str]] = {}):
        chat_gpt = ChatGPT()
        chat_gpt.messages = [Message(role="system", content=sys_prompt)]
        if reflections_to_gathered_files:
            all_reflections_string = ""
            for idx, (reflection, gathered_files) in enumerate(reflections_to_gathered_files.items()):
                formatted_reflection = reflection_prompt.format(
                    files_read="\n".join(gathered_files),
                    reflections_string=reflection,
                    idx=str(idx + 1),
                )
                all_reflections_string += f"\n{formatted_reflection}"
            formatted_reflections_prompt = reflections_prompt_prefix.format(
                all_reflections=all_reflections_string
            )
            updated_user_prompt = user_prompt + "\n" + formatted_reflections_prompt
        else:
            updated_user_prompt = user_prompt
        function_calls_string = chat_gpt.chat_anthropic(
            content=updated_user_prompt,
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
                    + "<function_call>\n<invoke>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</invoke>\n</function_calls>" + "\n\nIf you would like to submit the plan, call the submit function."
                bad_call_count += 1
                if bad_call_count >= 3:
                    return chat_gpt.messages # set to three, which seems alright
            try:
                function_calls_string = chat_gpt.chat_anthropic(
                    content=function_output,
                    model=CLAUDE_MODEL,
                    stop_sequences=["</function_call>"],
                )
            except Exception as e:
                logger.error(f"Error in chat_anthropic: {e}")
                # return all but the last message because it likely causes an error
                return chat_gpt.messages[:-1]
        return chat_gpt.messages
    for rollout_idx in range(NUM_ROLLOUTS):
        # operate on a deep copy of the repo context manager
        copied_repo_context_manager = deepcopy(repo_context_manager)
        message_results = perform_rollout(copied_repo_context_manager, reflections_to_read_files)
        rollout_stored_files = [snippet.file_path for snippet in copied_repo_context_manager.current_top_snippets]
        truncated_message_results = message_results[1:] # skip system prompt
        joined_messages = "\n\n".join([message.content for message in truncated_message_results])
        overall_score, message_to_contractor = EvaluatorAgent().evaluate_run(
            problem_statement=problem_statement, 
            run_text=joined_messages,
            stored_files=rollout_stored_files,
        )
        logger.info(f"Completed run {rollout_idx} with score: {overall_score} and reflection: {message_to_contractor}")
        if overall_score is None or message_to_contractor is None:
            continue # can't get any reflections here
        reflections_to_read_files[message_to_contractor] = rollout_stored_files
        rollouts_to_scores_and_rcms[rollout_idx] = (overall_score, copied_repo_context_manager)
        if overall_score >= 8:
            break
    # if we reach here, we have not found a good enough solution
    # select rcm from the best rollout
    all_scores_and_rcms = list(rollouts_to_scores_and_rcms.values())
    best_score, best_rcm = max(all_scores_and_rcms, key=lambda x: x[0])
    logger.info(f"Best score: {best_score}")
    return best_rcm

if __name__ == "__main__":
    try:
        from sweepai.utils.github_utils import get_installation_id
        from sweepai.utils.ticket_utils import prep_snippets

        organization_name = "sweepai"
        installation_id = get_installation_id(organization_name)
        cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")
        query = "allow 'sweep.yaml' to be read from the user/organization's .github repository. this is found in client.py and we need to change this to optionally read from .github/sweep.yaml if it exists there"
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
    except Exception as e:
        logger.error(f"context_pruning.py failed to run successfully with error: {e}")
        raise e
