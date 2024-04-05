from copy import deepcopy
from math import log
import os
import subprocess
import urllib
from dataclasses import dataclass, field, replace

import networkx as nx
import openai
from loguru import logger
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.config.client import SweepConfig
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.core.reflection_utils import EvaluatorAgent
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.convert_openai_anthropic import MockFunctionCall, mock_function_calls_to_string
from sweepai.utils.github_utils import ClonedRepo, MockClonedRepo
from sweepai.utils.modify_utils import post_process_rg_output
from sweepai.utils.openai_listwise_reranker import listwise_rerank_snippets
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.tree_utils import DirectoryTree

ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens
NUM_SNIPPETS_TO_SHOW_AT_START = 15
MAX_REFLECTIONS = 2

# TODO:
# - Add self-evaluation / chain-of-verification
# - Add list of tricks for finding definitions

anthropic_function_calls = """<tool_name>view_file</tool_name>
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
Adds a file to the context that needs to be read for context or modified to resolve the issue. Provide a code excerpt in the justification showcasing the file's relevance, i.e. how it provides important context or should be fixed. After using this tool, use `code_search` to find definitions of unknown functions/classes in the file.
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
<description>Explain why this file should be read for context or modified and what needs to be modified. Include a supporting code excerpt.</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>code_search</tool_name>
<description>
Passes the code_entity into ripgrep to search the entire codebase and return a list of files and line numbers where it appears. Useful for finding definitions of unknown types, classes and functions. Review the search results using `view_file` to determine relevance. Focus on definitions.
</description>
<parameters>
<parameter>
<name>code_entity</name>
<type>string</type>
<description>The code entity to search for. Should be a distinctive name, not a generic term. For functions, search for the definition syntax, e.g. 'def foo' in Python or 'function bar' or 'const bar' in JavaScript.</description>
</parameter>
<parameter>
<name>justification</name>
<type>string</type>
<description>Explain what information you expect to get from this search and why it's needed, e.g. "I need to find the definition of the Foo class to see what methods are available on Foo objects."</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>submit</tool_name>
<description>
Provides a detailed report of the issue and a complete plan to resolve it. The report should explain the root cause, expected behavior, files to read for context, and files to modify. The plan should outline the changes needed in each file. Write it for an outside contractor with no prior knowledge of the codebase or issue. Only call this tool once when you are absolutely certain you have all the necessary information.
</description>
<parameters>
<parameter>
<name>plan</name>
<type>string</type>
<description>The complete, detailed plan including background information, files to read for context, files to change, and the specific changes to make in each file.</description>
</parameter>
</parameters>
</tool_description>

You must call the tools using the specified XML format. Here are some generic examples to illustrate the format without referring to a specific task:

<examples>
Example 1 (calling multiple tools in parallel):
<function_calls>
<invoke>
<tool_name>view_file</tool_name>
<parameters>
<file_path>services/user_service.py</file_path>
<justification>The user request mentions modifying the get_user_by_id method in the UserService class. I need to view the user_service.py file to locate this method and determine what changes are needed.</justification>
</parameters>
</invoke>
</function_calls>

Example 2:
<function_calls>
<invoke>  
<tool_name>store_file</tool_name>
<parameters>
<file_path>models/user.py</file_path>
<justification>The User model is relevant for understanding the attributes of a User, especially the `deleted` flag that indicates if a user is soft-deleted. This excerpt shows the key parts of the model:
```python
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))  
    email = db.Column(db.String(100), unique=True)
    deleted = db.Column(db.Boolean, default=False)
```
</justification>
</parameters>
</invoke>
<invoke>
<tool_name>code_search</tool_name>
<parameters>
<code_entity>def get_user_by_id</code_entity>
<justification>I need to find the definition of the get_user_by_id method to see its current implementation and determine what changes are needed to support excluding deleted users.</justification>
</parameters>
</invoke>
</function_calls>

Example 4:
<function_calls>
<invoke>
<tool_name>submit</tool_name>
<parameters>
<plan>
To fix the issue of being able to access deleted users via the API:

Read the following files for context:
- models/user.py: Understand the User model and its `deleted` attribute. Key excerpt:
```python 
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) 
    email = db.Column(db.String(100), unique=True, nullable=False)
    deleted = db.Column(db.Boolean, default=False)
```

Modify user_service.py:
- In the `UserService` class, find the `get_user_by_id` method that fetches a user by ID
- Add a new optional parameter `include_deleted` with a default of `False` 
- In the method, check the value of `include_deleted`
- If `False`, update the database query to filter out users where `deleted` is `True`
- If `True`, no query changes needed
- Update the method's docstring for the new parameter and behavior

Modify app.py: 
- Find the `get_user` route handler
- Locate the call to `UserService.get_user_by_id()` in the route handler
- Add `include_deleted=True` to the `get_user_by_id()` call to include deleted users
</plan>
</parameters>
</invoke>
</function_calls>
</examples>

I will provide the tool's response after each <function_calls> block, then you may call another set of tools as you work towards a solution. Focus on the actual issue at hand rather than these illustrative examples."""

sys_prompt = """You are a brilliant engineer assigned to solve the following GitHub issue. Your task is to generate a complete, detailed plan to fully resolve the issue and identify all relevant files. A file is considered RELEVANT if it must be either modified or read to understand the necessary changes as part of the issue resolution process. 

It is critical that you identify and include every relevant line of code that should be either modified or read as context. Your goal is to generate an extremely detailed and accurate plan of code changes and relevant files for an intern who is unfamiliar with the codebase. 

You will do this by searching for and viewing files in the codebase to gather all the necessary information.

INSTRUCTIONS

Use the following iterative process:
1. View all files that seem relevant based on file paths and entities mentioned in the "User Request" and "Relevant Snippets". For example, if the class foo.bar.Bar is referenced, be sure to view foo/bar.py. Skip irrelevant files. Check all files referenced in the user request. If you can't find a specific module, also check the "Common modules" section.

2. Use code_search to find definitions for ALL unknown variables, classes, attributes, and functions. For instance, if the method foo(param1: typeX, param2: typeY) -> typeZ is used, search for the keywords typeX, typeY, and typeZ to find their definitions. If you want to use `user.deleted`, verify that the `deleted` attribute exists on the entity. View the relevant definition files. Make sure to view ALL files when using or changing any function input parameters, methods or attributes.

3. When you identify a relevant file, use store_file to add it to the context.

Repeat steps 1-3 until you are fully confident you have gathered all the necessary information detailing all entities used, variable names, attribute names, and files to read and modify.

4. Submit the final plan with the submit function. 

Here are the tools at your disposal. Call them until you have gathered all relevant information:

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

def escape_ripgrep(text):
    # Special characters to escape
    special_chars = ["(", "{"]
    for s in special_chars:
        text = text.replace(s, "\\" + s)
    return text

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
            import_tree_prompt.format(import_trees=self.import_trees.strip("\n"))
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
    # creates a copy of the RepoContextManager with a seperate ClonedRepo
    # this is done so that if you need deep copies of a RepoContextManager it will not affect the ClonedRepos of the 
    # other copies when one copy goes out of context since we do file operations of CloneRepo
    def copy_repo_context_manager(self):
        if not isinstance(self.cloned_repo, MockClonedRepo):
            new_cloned_repo = ClonedRepo(
                self.cloned_repo.repo_full_name,
                installation_id=self.cloned_repo.installation_id,
                token=self.cloned_repo.token,
                repo=self.cloned_repo.repo,
                branch=self.cloned_repo.branch,
            )
            return replace(self, cloned_repo=new_cloned_repo)
        return deepcopy(self)

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

def graph_retrieval(formatted_query: str, top_k_paths: list[str], rcm: RepoContextManager, G: nx.DiGraph):
    # TODO: tune these params
    top_paths_cutoff = 25
    num_rerank = 30
    selected_paths = rcm.top_snippet_paths[:10]
    top_k_paths = top_k_paths[:top_paths_cutoff]

    snippet_scores = rcm.snippet_scores
    for snippet, score in snippet_scores.items():
        if snippet.split(":")[0] in top_k_paths:
            snippet_scores[snippet] += 1

    personalization = {}

    for snippet in selected_paths:
        personalization[snippet] = 1

    try:
        personalized_pagerank_scores = nx.pagerank(G, personalization=personalization, alpha=0.85)
        unpersonalized_pagerank_scores = nx.pagerank(G, alpha=0.85)

        # tfidf style
        normalized_pagerank_scores = {path: score * log(1 / (1e-6 + unpersonalized_pagerank_scores[path])) for path, score in personalized_pagerank_scores.items()}

        top_pagerank_scores = sorted(normalized_pagerank_scores.items(), key=lambda x: x[1], reverse=True)
        
        top_pagerank_paths = [path for path, _score in top_pagerank_scores]

        distilled_file_path_list = []

        for file_path, score in top_pagerank_scores:
            if file_path.endswith(".js") and file_path.replace(".js", ".ts") in top_pagerank_paths:
                continue
            if file_path in top_k_paths:
                continue
            if "generated" in file_path or "mock" in file_path or "test" in file_path:
                continue
            try:
                rcm.cloned_repo.get_file_contents(file_path)
            except FileNotFoundError:
                continue
            distilled_file_path_list.append(file_path)
        
        # Rerank once
        reranked_snippets = []
        for file_path in distilled_file_path_list[:num_rerank]:
            contents = rcm.cloned_repo.get_file_contents(file_path)
            reranked_snippets.append(Snippet(
                content=contents,
                start=0,
                end=contents.count("\n") + 1,
                file_path=file_path,
            ))
        reranked_snippets = listwise_rerank_snippets(formatted_query, reranked_snippets, prompt_type="graph")
        distilled_file_path_list[:num_rerank] = [snippet.file_path for snippet in reranked_snippets]

        return distilled_file_path_list
    except Exception as e:
        logger.error(e)
        return []

@file_cache(ignore_params=["repo_context_manager", "override_import_graph"])
def integrate_graph_retrieval(formatted_query: str, repo_context_manager: RepoContextManager, override_import_graph: nx.DiGraph = None):
    num_graph_retrievals = 25
    repo_context_manager, import_graph = parse_query_for_files(formatted_query, repo_context_manager)
    if override_import_graph:
        import_graph = override_import_graph
    if import_graph:
        # Graph retrieval can fail and return [] if the graph is not found or pagerank does not converge
        # Happens especially when graph has multiple components
        graph_retrieved_files = graph_retrieval(formatted_query, repo_context_manager.top_snippet_paths, repo_context_manager, import_graph)
        if graph_retrieved_files:
            sorted_snippets = sorted(
                repo_context_manager.snippets,
                key=lambda snippet: repo_context_manager.snippet_scores[snippet.denotation],
                reverse=True,
            )
            snippets = []
            for file_path in graph_retrieved_files:
                for snippet in sorted_snippets[50 - num_graph_retrievals:]:
                    if snippet.file_path == file_path:
                        snippets.append(snippet)
                        break
            graph_retrieved_files = graph_retrieved_files[:num_graph_retrievals]
            repo_context_manager.read_only_snippets = snippets[:len(graph_retrieved_files)]
            repo_context_manager.current_top_snippets = repo_context_manager.current_top_snippets[:50 - num_graph_retrievals]
    return repo_context_manager, import_graph

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
    # graph_retrieved_files = graph_retrieval(rcm.top_snippet_paths, rcm, import_graph)[:15]
    graph_retrieved_files = [snippet.file_path for snippet in rcm.read_only_snippets]
    if code_files_in_query:
        for file in code_files_in_query:
            # fetch direct parent and children
            representation = (
                f"\nThe file '{file}' has the following import structure: \n"
                + build_full_hierarchy(import_graph, file, 2)
            )
            if graph_retrieved_files:
                representation += "\n\nThe following modules may contain helpful services or utility functions:\n- " + "\n- ".join(graph_retrieved_files)
            rcm.add_import_trees(representation)
    # if there are no code_files_in_query, we build import trees for the top 5 snippets
    else:
        for snippet in rcm.current_top_snippets[:5]:
            file_path = snippet.file_path
            representation = (
                f"\nThe file '{file_path}' has the following import structure: \n"
                + build_full_hierarchy(import_graph, file_path, 2)
            )
            if graph_retrieved_files:
                representation += "\n\nThe following modules may contain helpful services or utility functions:\n- " + "\n-".join(graph_retrieved_files)
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
    seed: int = None,
    import_graph: nx.DiGraph = None,
    ticket_progress: TicketProgress = None,
    chat_logger: ChatLogger = None,
):
    logger.info("Seed: " + str(seed))
    try:
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
        old_relevant_snippets = deepcopy(repo_context_manager.current_top_snippets)
        old_read_only_snippets = deepcopy(repo_context_manager.read_only_snippets)
        try:
            repo_context_manager = context_dfs(
                user_prompt,
                repo_context_manager,
                problem_statement=query,
            )
        except openai.BadRequestError as e:  # sometimes means that run has expired
            logger.exception(e)
        # repo_context_manager.current_top_snippets += old_relevant_snippets[:25 - len(repo_context_manager.current_top_snippets)]
        # Add stuffing until context limit
        max_chars = 140000 * 3.5 # 120k tokens
        counter = sum([len(snippet.get_snippet(False, False)) for snippet in repo_context_manager.current_top_snippets]) + sum(
            [len(snippet.get_snippet(False, False)) for snippet in repo_context_manager.read_only_snippets]
        )
        for snippet, read_only_snippet in zip(old_relevant_snippets, old_read_only_snippets):
            if not any(context_snippet.file_path == snippet.file_path for context_snippet in repo_context_manager.current_top_snippets):
                counter += len(snippet.get_snippet(False, False))
                if counter > max_chars:
                    break
                repo_context_manager.current_top_snippets.append(snippet)
            if not any(context_snippet.file_path == read_only_snippet.file_path for context_snippet in repo_context_manager.read_only_snippets):
                counter += len(read_only_snippet.get_snippet(False, False))
                if counter > max_chars:
                    break
                repo_context_manager.read_only_snippets.append(read_only_snippet)
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
        function_calls_string.strip("\n") + "\n</function_calls>"
    )  # add end tag
    if len(function_calls) > 0:
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</function_calls>"
        )  # add end tag to assistant message
        return function_calls

    # try adding </invoke> tag as well
    function_calls = MockFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</invoke>\n</function_calls>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</invoke>\n</function_calls>"
        )
        return function_calls
    # try adding </parameters> tag as well
    function_calls = MockFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n")
        + "\n</parameters>\n</invoke>\n</function_calls>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n")
            + "\n</parameters>\n</invoke>\n</function_calls>"
        )
    return function_calls


def handle_function_call(
    repo_context_manager: RepoContextManager, function_call: MockFunctionCall, llm_state: dict[str, str]
):
    function_name = function_call.function_name
    function_input = function_call.function_parameters
    logger.info(f"Tool Call: {function_name} {function_input}")
    file_path = function_input.get("file_path")
    valid_path = False
    output_prefix = f"Output for {function_name}:\n"
    output = ""
    current_top_snippets_string = "\n".join(
        [snippet.denotation for snippet in repo_context_manager.current_top_snippets]
    )
    if function_name == "code_search":
        code_entity = f'"{function_input["code_entity"]}"'  # handles cases with two words
        code_entity = escape_ripgrep(code_entity) # escape special characters
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
                rg_output_pretty, file_output_dict = post_process_rg_output(
                    repo_context_manager.cloned_repo.repo_dir, SweepConfig(), rg_output
                )
                fetched_files = [fetched_file for fetched_file in file_output_dict.keys()]
                fetched_files_that_are_stored = [
                    fetched_file
                    for fetched_file in fetched_files
                    if fetched_file in [snippet.file_path for snippet in repo_context_manager.current_top_snippets]
                ]
                joined_files_string = "\n".join(fetched_files_that_are_stored)
                stored_files_string = f'The following files have been stored already:\n{joined_files_string}.\n' if fetched_files_that_are_stored else ""
                output = (
                    f"SUCCESS: Here are the code_search results:\n<code_search_results>\n{rg_output_pretty}<code_search_results>\n" +
                    stored_files_string + 
                    "Use the `view_file` tool to determine which non-stored files are most relevant to solving the issue. Use `store_file` to add any important non-stored files to the context."
                )
            else:
                output = f"FAILURE: No results found for code_entity: {code_entity} in the entire codebase. Please try a new code_entity. Consider trying different whitespace or case variations."
        except Exception as e:
            logger.error(
                f"FAILURE: An Error occured while trying to find the code_entity {code_entity}: {e}"
            )
            output = f"FAILURE: No results found for code_entity: {code_entity} in the entire codebase. Please try a new code_entity. Consider trying different whitespace or case variations."
    elif function_name == "view_file":
        try:
            file_contents = repo_context_manager.cloned_repo.get_file_contents(
                file_path
            )
            valid_path = True
            if valid_path:
                
                output = f'SUCCESS: Here are the contents of `{file_path}:`\n<source>\n{file_contents}\n</source>'
                if file_path not in [snippet.file_path for snippet in repo_context_manager.current_top_snippets]:
                    suffix = f'\nIf you are CERTAIN this file is RELEVANT, call store_file with the same parameters ({{"file_path": "{file_path}"}}).'
                else:
                    suffix = '\nThis file has already been stored.'
                output += suffix
            else:
                output = (
                    f"FAILURE: The file path '{file_path}' does not exist. Please check the path and try again."
                )
        except FileNotFoundError:
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
                    f"SUCCESS: {file_path} was added to the context. It will be used as a reference or modified to resolve the issue. Here are the current selected snippets:\n{current_top_snippets_string}"
                    if valid_path
                    else f"FAILURE: The file path '{file_path}' does not exist. Please check the path and try again."
                )
    elif function_name == "submit":
        plan = function_input.get("plan")
        repo_context_manager.update_issue_report_and_plan(f"# Highly Suggested Plan:\n\n{plan}\n\n")
        output = PLAN_SUBMITTED_MESSAGE
    else:
        output = f"FAILURE: Invalid tool name {function_name}"
    justification = (
        function_input["justification"] if "justification" in function_input else ""
    )
    logger.info(
        f"Tool Call: {function_name}\n{justification}\n{output}"
    )
    return (output_prefix + output)


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
<rating>
Rating from previous attempt: {score} / 10
</rating>
<feedback>
Reviewer feedback on previous attempt:
{reflections_string}
</feedback>
</attempt_and_feedback_{idx}>"""

def format_reflections(reflections_to_gathered_files: dict[str, tuple[list[str], int]]) -> str:
    formatted_reflections_prompt = ""
    if not reflections_to_gathered_files:
        return formatted_reflections_prompt
    all_reflections_string = "\n"
    # take only the MAX_REFLECTIONS sorted by score
    top_reflections = sorted(
        reflections_to_gathered_files.items(), key=lambda x: x[1][1] * 100 + len(x[1][0]), reverse=True # break ties by number of files stored
    )[:MAX_REFLECTIONS]
    for idx, (reflection, (gathered_files, score)) in enumerate(top_reflections):
        formatted_reflection = reflection_prompt.format(
            files_read="\n".join(gathered_files),
            reflections_string=reflection,
            score=str(score),
            idx=str(idx + 1),
        )
        all_reflections_string += f"\n{formatted_reflection}"
    formatted_reflections_prompt = reflections_prompt_prefix.format(
        all_reflections=all_reflections_string
    )
    return formatted_reflections_prompt

def context_dfs(
    user_prompt: str,
    repo_context_manager: RepoContextManager,
    problem_statement: str,
) -> bool | None:
    MAX_ITERATIONS = 30 # Tuned to 30 because haiku is cheap
    NUM_ROLLOUTS = 1
    SCORE_THRESHOLD = 8 # good score
    STOP_AFTER_SCORE_THRESHOLD_IDX = 0 # stop after the first good score and past this index
    MAX_PARALLEL_FUNCTION_CALLS = 3
    repo_context_manager.current_top_snippets = []
    # initial function call
    reflections_to_read_files = {}
    rollouts_to_scores_and_rcms = {}
    def perform_rollout(repo_context_manager: RepoContextManager, reflections_to_gathered_files: dict[str, tuple[list[str], int]]) -> list[Message]:
        formatted_reflections_prompt = format_reflections(reflections_to_gathered_files)
        updated_user_prompt = user_prompt + formatted_reflections_prompt
        chat_gpt = ChatGPT()
        chat_gpt.messages = [Message(role="system", content=sys_prompt + formatted_reflections_prompt)]
        function_calls_string = chat_gpt.chat_anthropic(
            content=updated_user_prompt,
            stop_sequences=["</function_calls>"],
            model=CLAUDE_MODEL,
            message_key="user_request",
        )
        bad_call_count = 0
        llm_state = {} # persisted across one rollout
        for _ in range(MAX_ITERATIONS):
            function_calls = validate_and_parse_function_calls(
                function_calls_string, chat_gpt
            )
            function_outputs = ""
            for function_call in function_calls[:MAX_PARALLEL_FUNCTION_CALLS]:
                function_outputs += handle_function_call(repo_context_manager, function_call, llm_state) + "\n"
                if PLAN_SUBMITTED_MESSAGE in function_outputs:
                    return chat_gpt.messages
            if len(function_calls) == 0:
                function_outputs = "FAILURE: No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n" \
                    + "<function_calls>\n<invoke>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</invoke>\n</function_calls>" + "\n\nIf you are ready to submit the plan, call the submit function."
                bad_call_count += 1
                if bad_call_count >= 3:
                    return chat_gpt.messages # set to three, which seems alright
            if len(function_calls) > MAX_PARALLEL_FUNCTION_CALLS:
                remaining_function_calls = function_calls[MAX_PARALLEL_FUNCTION_CALLS:]
                remaining_function_calls_string = mock_function_calls_to_string(remaining_function_calls)
                function_outputs += "WARNING: You requested more than 3 function calls at once. Only the first 3 function calls have been processed. The unprocessed function calls were:\n<unprocessed_function_calls>\n" + remaining_function_calls_string + "\n</unprocessed_function_calls>"
            try:
                function_calls_string = chat_gpt.chat_anthropic(
                    content=function_outputs,
                    model=CLAUDE_MODEL,
                    stop_sequences=["</function_calls>"],
                )
            except Exception as e:
                logger.error(f"Error in chat_anthropic: {e}")
                # return all but the last message because it likely causes an error
                return chat_gpt.messages[:-1]
        return chat_gpt.messages
    for rollout_idx in range(NUM_ROLLOUTS):
        # operate on a deep copy of the repo context manager
        copied_repo_context_manager = repo_context_manager.copy_repo_context_manager()
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
        reflections_to_read_files[message_to_contractor] = rollout_stored_files, overall_score
        rollouts_to_scores_and_rcms[rollout_idx] = (overall_score, copied_repo_context_manager)
        if overall_score >= SCORE_THRESHOLD and len(rollout_stored_files) > STOP_AFTER_SCORE_THRESHOLD_IDX:
            break
    # if we reach here, we have not found a good enough solution
    # select rcm from the best rollout
    all_scores_and_rcms = list(rollouts_to_scores_and_rcms.values())
    best_score, best_rcm = max(all_scores_and_rcms, key=lambda x: x[0] * 100 + len(x[1].current_top_snippets)) # sort first on the highest score, break ties with length of current_top_snippets
    for score, rcm in all_scores_and_rcms:
        logger.info(f"Rollout score: {score}, Rollout files: {[snippet.file_path for snippet in rcm.current_top_snippets]}")
    logger.info(f"Best score: {best_score}, Best files: {[snippet.file_path for snippet in best_rcm.current_top_snippets]}")
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
