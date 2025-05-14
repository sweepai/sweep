from copy import deepcopy
from math import log
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
from sweepai.logn.cache import file_cache
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall, mock_function_calls_to_string
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.ripgrep_utils import post_process_rg_output
from sweepai.utils.openai_listwise_reranker import listwise_rerank_snippets
from sweepai.utils.progress import AssistantConversation, TicketProgress
from sweepai.utils.tree_utils import DirectoryTree

ASSISTANT_MAX_CHARS = 4096 * 4 * 0.95  # ~95% of 4k tokens
NUM_SNIPPETS_TO_SHOW_AT_START = 15
MAX_REFLECTIONS = 1
MAX_ITERATIONS = 25
NUM_ROLLOUTS = 1 # dev speed
SCORE_THRESHOLD = 8 # good score
STOP_AFTER_SCORE_THRESHOLD_IDX = 0 # stop after the first good score and past this index
MAX_PARALLEL_FUNCTION_CALLS = 1
NUM_BAD_FUNCTION_CALLS = 5

# TODO:
# - Add self-evaluation / chain-of-verification

anthropic_function_calls = """<tool_description>
<tool_name>code_search</tool_name>
<description>
Passes the code_entity into ripgrep to search the entire codebase and return a list of files and line numbers where it appears. Useful for finding definitions, usages, and references to types, classes, functions, and other entities that may be relevant. Review the search results using `view_files` to determine relevance and discover new files to explore.
</description>
<parameters>
<parameter>
<name>analysis</name>
<type>string</type>
<description>Explain what new information you expect to discover from this search and why it's needed to get to the root of the issue. Focus on unknowns rather than already stored information.</description>
</parameter>
<parameter>
<name>code_entity</name>
<type>string</type>
<description>
The code entity to search for. This must be a distinctive name, not a generic term. For functions, search for the definition syntax, e.g. 'def foo' in Python or 'function bar' or 'const bar' in JavaScript. Trace dependencies of critical functions/classes, follow imports to find definitions, and explore how key entities are used across the codebase.
</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>view_files</tool_name>
<description>
Retrieves the contents of the specified file(s). After viewing new files, use `code_search` on relevant entities to continue discovering potentially relevant files. You may view three files per tool call. Prioritize viewing new files over ones that are already stored.
</description>
<parameters>
<parameter>
<name>analysis</name>
<type>string</type>
<description>Explain what new information viewing these files will provide and why it's necessary to resolve the issue. Avoid restating already known information.</description>
</parameter>
<parameter>
<name>first_file_path</name>
<type>string</type>
<description>The path of a new file to view.</description>
</parameter>
<parameter>
<name>second_file_path</name>
<type>string</type>
<description>The path of another new file to view (optional).</description>
</parameter>
<parameter>
<name>third_file_path</name>
<type>string</type>
<description>The path of a third new file to view (optional).</description>
</parameter>
</parameters>
</tool_description>

<tool_description>
<tool_name>store_file</tool_name>
<description>
Adds a newly discovered file that provides important context or may need modifications to the list of stored files. You may only store one new file per tool call. Avoid storing files that have already been added.
</description>
<parameters>
<parameter>
<name>analysis</name>
<type>string</type>
<description>Explain what new information this file provides, why it's important for understanding and resolving the issue, and what potentially needs to be modified. Include a brief supporting code excerpt.</description>
</parameter>
<parameter>
<name>file_path</name>
<type>string</type>
<description>The path of the newly discovered relevant file to store.</description>
</parameter>
</parameters>
</tool_description>

You MUST call the tools using this exact XML format:

<function_call>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_call>

Here is an example illustrating a complex code search to discover new relevant information:

<example>
<function_call>
<invoke>
<tool_name>code_search</tool_name>
<parameters>
<analysis>The get_user_by_id method likely queries from a User model or database table. I need to search for references to "User" to find where and how user records are defined, queried and filtered in order to determine what changes are needed to support excluding deleted users from the get_user_by_id results.</analysis>
<code_entity>User</code_entity>
</parameters>
</invoke>
</function_call>
</example>

Remember, your goal is to discover and store ALL files that are relevant to solving the issue. Perform targeted searches to uncover new information, view new files to understand the codebase, and avoid re-analyzing already stored files."""

sys_prompt = """You are a brilliant engineer assigned to solve the following GitHub issue. Your task is to search through the codebase and locate ALL files that are RELEVANT to resolving the issue. A file is considered RELEVANT if it provides important context or may need to be modified as part of the solution.

You will begin with a small set of stored relevant files. However, it is critical that you identify every additional relevant file by exhaustively searching the codebase. Your goal is to generate an extremely comprehensive list of files for an intern engineer who is completely unfamiliar with the codebase. Prioritize finding all relevant files over perfect precision - it's better to include a few extra files than to miss a key one.

To accomplish this, you will iteratively search for and view new files to gather all the necessary information. Follow these steps:

1. Perform targeted code searches to find definitions, usages, and references for ALL unknown variables, classes, attributes, functions and other entities that may be relevant based on the currently stored files and issue description. Be creative and think critically about what to search for to get to the root of the issue. 

2. View new files from the search results that seem relevant. Avoid viewing files that are already stored, and instead focus on discovering new information.

3. Store additional files that provide important context or may need changes based on the search results, viewed files, and issue description. 

Repeat steps 1-3, searching and exploring the codebase exhaustively until you are confident you have found all relevant files. Prioritize discovering new information over re-analyzing what is already known.

Here are the tools at your disposal:
""" + anthropic_function_calls

unformatted_user_prompt = """\
## Stored Files
DO NOT CALL THE STORE OR VIEW TOOLS ON THEM AGAIN AS THEY HAVE ALREADY BEEN STORED.
<stored_files>
{snippets_in_repo}
</stored_files>

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

def run_ripgrep_command(code_entity, repo_dir, *args):
    # Updated for the new context
    rg_command = [
        "rg",
        "-n",
        "-w",
        "-i",
        "-C=3",
        "--heading",
        code_entity,
        repo_dir,
    ]
    result = subprocess.run(
        " ".join(rg_command), text=True, shell=True, capture_output=True
    )
    return result.stdout

@staticmethod
def can_add_snippet(snippet: Snippet, current_snippets: list[Snippet]):
    return (
        len(snippet.xml) + sum([len(snippet.xml) for snippet in current_snippets])
        <= ASSISTANT_MAX_CHARS
    )


@dataclass
class RepoContextManager:
    cloned_repo: ClonedRepo
    current_top_snippets: list[Snippet] = field(default_factory=list)
    read_only_snippets: list[Snippet] = field(default_factory=list)
    test_current_top_snippets: list[Snippet] = field(default_factory=list)
    issue_report_and_plan: str = ""
    import_trees: str = ""
    relevant_file_paths: list[str] = field(
        default_factory=list
    )  # a list of file paths that appear in the user query
    # UNUSED:
    snippets: list[Snippet] = field(default_factory=list) # This is actually used in benchmarks
    snippet_scores: dict[str, float] = field(default_factory=dict)
    current_top_tree: str | None = None
    dir_obj: DirectoryTree | None = None

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
        files_in_repo_str = ""
        stored_files = set()
        for idx, snippet in enumerate(list(dict.fromkeys(self.current_top_snippets))[:NUM_SNIPPETS_TO_SHOW_AT_START]):
            if snippet.file_path in stored_files:
                continue
            stored_files.add(snippet.file_path)
            snippet_str = \
f'''
<stored_file index="{idx + 1}">
<file_path>{snippet.file_path}</file_path>
<source>
{snippet.content}
</source>
</stored_file>
'''
            files_in_repo_str += snippet_str
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
            snippets_in_repo=files_in_repo_str,
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

    def boost_snippets_to_top(self, snippets_to_boost: list[Snippet], code_files_in_query: list[str]):
        # self.dir_obj.add_file_paths([snippet.file_path for snippet in snippets_to_boost])
        for snippet in snippets_to_boost:
            # get first positions of all snippets that are in the code_files_in_query
            all_first_in_query_positions = [self.top_snippet_paths.index(file_path) for file_path in code_files_in_query if file_path in self.top_snippet_paths]
            last_mentioned_result_index = (max(all_first_in_query_positions, default=-1) + 1) if all_first_in_query_positions else 0
            # insert after the last mentioned result
            self.current_top_snippets.insert(max(0, last_mentioned_result_index), snippet)

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

# @file_cache(ignore_params=["rcm", "G"])
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
        @file_cache()
        def get_distilled_file_paths(formatted_query, top_k_paths):
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
            return distilled_file_path_list
        distilled_file_path_list = get_distilled_file_paths(formatted_query, top_k_paths)
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

# @file_cache(ignore_params=["repo_context_manager", "override_import_graph"]) # can't cache this because rcm is stateful
def integrate_graph_retrieval(formatted_query: str, repo_context_manager: RepoContextManager, override_import_graph: nx.DiGraph = None):
    repo_context_manager, import_graph = parse_query_for_files(formatted_query, repo_context_manager)
    if override_import_graph:
        import_graph = override_import_graph
    # if import_graph:
    #     # Graph retrieval can fail and return [] if the graph is not found or pagerank does not converge
    #     # Happens especially when graph has multiple components
    #     graph_retrieved_files = graph_retrieval(formatted_query, sorted(repo_context_manager.top_snippet_paths), repo_context_manager, import_graph) # sort input for caching
    #     if graph_retrieved_files:
    #         sorted_snippets = sorted(
    #             repo_context_manager.snippets,
    #             key=lambda snippet: repo_context_manager.snippet_scores[snippet.denotation],
    #             reverse=True,
    #         )
    #         snippets = []
    #         for file_path in graph_retrieved_files:
    #             for snippet in sorted_snippets[50 - num_graph_retrievals:]:
    #                 if snippet.file_path == file_path:
    #                     snippets.append(snippet)
    #                     break
    #         graph_retrieved_files = graph_retrieved_files[:num_graph_retrievals]
    #         repo_context_manager.read_only_snippets = snippets[:len(graph_retrieved_files)]
    #         repo_context_manager.current_top_snippets = repo_context_manager.current_top_snippets[:50 - num_graph_retrievals]
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
                rcm.boost_snippets_to_top(code_snippets, code_files_in_query)
            except Exception as e:
                logger.error(
                    f"Tried to add code file found in query but recieved error: {e}, skipping and continuing to next one."
                )
    return rcm

def generate_import_graph_text(graph):
  # Create a dictionary to store the import relationships
  import_dict = {}

  # Iterate over each node (file) in the graph
  for node in graph.nodes():
    # Get the files imported by the current file
    imported_files = list(graph.successors(node))

    # Add the import relationships to the dictionary
    if imported_files:
      import_dict[node] = imported_files
    else:
      import_dict[node] = []

  # Generate the text-based representation
  final_text = ""
  visited_files = set()
  for file, imported_files in sorted(import_dict.items(), key=lambda x: x[0]):
    if file not in visited_files:
      final_text += generate_file_imports(graph, file, visited_files, "")
      final_text += "\n"

  # Add files that are not importing any other files
  non_importing_files = [
      file for file, imported_files in import_dict.items()
      if not imported_files and file not in visited_files
  ]
  if non_importing_files:
    final_text += "\n".join(non_importing_files)

  return final_text


def generate_file_imports(graph,
                          file,
                          visited_files,
                          last_successor,
                          indent_level=0):
  # if you just added this file as a successor, you don't need to add it again
  visited_files.add(file)
  text = "  " * indent_level + f"{file}\n" if file != last_successor else ""

  for imported_file in graph.successors(file):
    text += "  " * (indent_level + 1) + f"──> {imported_file}\n"
    if imported_file not in visited_files:
      text += generate_file_imports(graph, imported_file, visited_files,
                                    imported_file, indent_level + 2)

  return text

# fetch all files mentioned in the user query
def parse_query_for_files(
    query: str, rcm: RepoContextManager
) -> tuple[RepoContextManager, nx.DiGraph]:
    MAX_FILES_TO_ADD = 5
    code_files_to_add = []
    code_files_to_check = set(list(rcm.cloned_repo.get_file_list()))
    code_files_uri_encoded = [
        urllib.parse.quote(file_path) for file_path in code_files_to_check
    ]
    # check if any code files are mentioned in the query
    for file, file_uri_encoded in zip(code_files_to_check, code_files_uri_encoded):
        if file in query or file_uri_encoded in query:
            code_files_to_add.append((file, file))
        # check this separately to match a/b/c.py with b/c.py
        elif len(file.split('/')) >= 2:
            last_two_parts = '/'.join(file.split('/')[-2:])
            if (last_two_parts in query or urllib.parse.quote(last_two_parts) in query) and len(last_two_parts) > 5:
                # this can be improved by bumping out other matches if it's a "better" match (e.g. more specific)
                code_files_to_add.append((file, last_two_parts))
    # sort by where the match was found in the query
    code_files_to_add = sorted(
        code_files_to_add,
        key=lambda x: query.index(x[1]) if x[1] in query else urllib.parse.unquote(query).index(x[1]), # must exist in query because we matched something
    )
    # convert to a deduplicated list of file paths
    code_files_to_add = list(dict.fromkeys([file for file, _ in code_files_to_add]))
    for code_file in code_files_to_add[:MAX_FILES_TO_ADD]:
        rcm.append_relevant_file_paths(code_file)
    return rcm, None


# do not ignore repo_context_manager
# @file_cache(ignore_params=["seed", "ticket_progress", "chat_logger"])
def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
    seed: int = None,
    import_graph: nx.DiGraph = None,
    num_rollouts: int = NUM_ROLLOUTS,
    ticket_progress = None,
    chat_logger = None,
) -> RepoContextManager:
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
        return repo_context_manager # Temporarily disabled context
        chat_gpt = ChatGPT()
        chat_gpt.messages = [Message(role="system", content=sys_prompt)]
        old_relevant_snippets = deepcopy(repo_context_manager.current_top_snippets)
        old_read_only_snippets = deepcopy(repo_context_manager.read_only_snippets)
        try:
            repo_context_manager = context_dfs(
                user_prompt,
                repo_context_manager,
                problem_statement=query,
                num_rollouts=num_rollouts,
            )
        except openai.BadRequestError as e:  # sometimes means that run has expired
            logger.exception(e)
        repo_context_manager.current_top_snippets.extend(old_relevant_snippets)
        repo_context_manager.read_only_snippets.extend(old_read_only_snippets)
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
) -> list[AnthropicFunctionCall]:
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</function_call>"
    )  # add end tag
    if len(function_calls) > 0:
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</function_call>"
        )  # add end tag to assistant message
        return function_calls

    # try adding </invoke> tag as well
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
        function_calls_string.strip("\n") + "\n</invoke>\n</function_call>"
    )
    if len(function_calls) > 0:
        # update state of chat_gpt
        chat_gpt.messages[-1].content = (
            chat_gpt.messages[-1].content.rstrip("\n") + "\n</invoke>\n</function_call>"
        )
        return function_calls
    # try adding </parameters> tag as well
    function_calls = AnthropicFunctionCall.mock_function_calls_from_string(
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
    repo_context_manager: RepoContextManager, function_call: AnthropicFunctionCall, llm_state: dict[str, str]
):
    function_name = function_call.function_name
    function_input = function_call.function_parameters
    logger.info(f"Tool Call: {function_name} {function_input}")
    file_path = function_input.get("file_path", None)
    valid_path = False
    output_prefix = f"Output for {function_name}:\n"
    output = ""
    current_top_snippets_string = "\n".join(
        list(dict.fromkeys([snippet.file_path for snippet in repo_context_manager.current_top_snippets]))
    )
    if function_name == "code_search":
        code_entity = f'"{function_input["code_entity"]}"'  # handles cases with two words
        code_entity = escape_ripgrep(code_entity) # escape special characters
        try:
            rg_output = run_ripgrep_command(code_entity, repo_context_manager.cloned_repo.repo_dir)
            if rg_output:
                # post process rip grep output to be more condensed
                rg_output_pretty, file_output_dict, file_to_num_occurrences = post_process_rg_output(
                    repo_context_manager.cloned_repo.repo_dir, SweepConfig(), rg_output
                )
                # return results first by occurrences then by alphabetical order
                non_stored_files = sorted([
                    file_path
                    for file_path in file_output_dict
                    if file_path not in repo_context_manager.top_snippet_paths
                ], key=lambda x: (-file_to_num_occurrences[x], x))
                non_stored_files = [file_path + f" ({file_to_num_occurrences[file_path]} occurrences)" for file_path in non_stored_files]
                non_stored_files_string = "These search results have not been stored:\n<non_stored_search_results>\n" + "\n".join(non_stored_files) + "\n</non_stored_search_results>\n" if non_stored_files else "All of the files above have already been stored. Search for a new term.\n"
                if len(file_output_dict) <= 10:
                    output = (
                        f"SUCCESS: Here are the code_search results:\n<code_search_results>\n{rg_output_pretty}<code_search_results>\n" +
                        non_stored_files_string + 
                        "Use the `view_files` tool to read the most relevant non-stored files. Use `store_file` to add any important non-stored files to the context. DO NOT VIEW FILES THAT HAVE BEEN STORED."
                    )
                else:
                    output = (
                        f"SUCCESS: Here are the code_search results:\n<code_search_results>\n{rg_output_pretty}<code_search_results>\n" +
                        non_stored_files_string + "Prioritize viewing the non-stored files with the most occurrences. Use the `view_files` tool to read the most relevant non-stored files. Use `store_file` to add any important non-stored files to the context. DO NOT VIEW FILES THAT HAVE BEEN STORED."
                    )
                # too many prompt it to search more specific
            else:
                output = f"FAILURE: No results found for code_entity: {code_entity} in the entire codebase. Please try a new code_entity. Consider trying different whitespace or a truncated version of this code_entity."
        except Exception as e:
            logger.error(
                f"FAILURE: An Error occured while trying to find the code_entity {code_entity}: {e}"
            )
            output = f"FAILURE: No results found for code_entity: {code_entity} in the entire codebase. Please try a new code_entity. Consider trying different whitespace or a truncated version of this code_entity."
    elif function_name == "view_files":
        output = ""
        all_viewed_files = [function_input.get("first_file_path", ""), function_input.get("second_file_path", ""), function_input.get("file_path", "")]
        all_viewed_files = [file_path for file_path in all_viewed_files if file_path]
        for file_path in all_viewed_files:
            try:
                file_contents = repo_context_manager.cloned_repo.get_file_contents(
                    file_path
                )
                # check if file has been viewed already
                # function_call_history = llm_state.get("function_call_history", [])
                # # unnest 2d list
                # previous_function_calls = [
                #     call for sublist in function_call_history for call in sublist
                # ]
                # previously_viewed_files = list(dict.fromkeys(previously_viewed_files))
                # if file_path in previously_viewed_files:
                #     previously_viewed_files_str = "\n".join(previously_viewed_files)
                #     output = f"WARNING: `{file_path}` has already been viewed. Please refer to the file in your previous function call. These files have already been viewed:\n{previously_viewed_files_str}"
                if file_path not in [snippet.file_path for snippet in repo_context_manager.current_top_snippets]:
                    output += f'SUCCESS: Here are the contents of `{file_path}`:\n<source>\n{file_contents}\n</source>\nYou can use the `store_file` tool to add this file to the context.'
                else:
                    output += f"FAILURE: {file_path} has already been stored. Please view a new file."
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
                output += f"FAILURE: {file_path} does not exist. Did you mean:\n{similar_file_paths}\n"
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
            if snippet.file_path in current_top_snippets_string:
                output = f"FAILURE: {get_stored_files(repo_context_manager)}"
            else:
                repo_context_manager.add_snippets([snippet])
                current_top_snippets_string = "\n".join(
                    list(dict.fromkeys([snippet.file_path for snippet in repo_context_manager.current_top_snippets]))
                )
                output = (
                    f"SUCCESS: {file_path} was added to the stored_files. It will be used as a reference or modified to resolve the issue."
                    if valid_path
                    else f"FAILURE: The file path '{file_path}' does not exist. Please check the path and try again."
                )
    elif function_name == "submit":
        plan = function_input.get("plan")
        repo_context_manager.update_issue_report_and_plan(f"# Highly Suggested Plan:\n\n{plan}\n\n")
        output = PLAN_SUBMITTED_MESSAGE
    else:
        output = f"FAILURE: Invalid tool name {function_name}"
    analysis = (
        function_input["analysis"] if "analysis" in function_input else ""
    )
    logger.info(
        f"Tool Call: {function_name}\n{analysis}\n{output}"
    )
    return (output_prefix + output)


reflections_prompt_prefix = """
CRITICAL FEEDBACK - READ CAREFULLY AND ADDRESS ALL POINTS
<critical_feedback_to_address>
Here is the feedback from your previous attempt. You MUST read this extremely carefully and follow ALL of the reviewer's advice. If they tell you to store specific files, view store them first. If you do not fully address this feedback you will fail to retrieve all of the relevant files.
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

def render_all_attempts(function_call_histories: list[list[list[AnthropicFunctionCall]]]) -> str:
    formatted_attempts = ""
    for idx, function_call_history in enumerate(function_call_histories):
        formatted_function_calls = render_function_calls_for_attempt(function_call_history)
        formatted_attempts += f"<attempt_{idx}>\n{formatted_function_calls}\n</attempt_{idx}>"
    return formatted_attempts

def render_function_calls_for_attempt(function_call_history: list[list[AnthropicFunctionCall]]) -> str:
    formatted_function_calls = ""
    idx = 0
    for function_calls in function_call_history:
        for function_call in function_calls:
            function_call.function_parameters.pop("analysis", None) # remove analysis
            function_call_cleaned_string = function_call.function_name + " | " + "\n".join([str(k) + " | " + str(v) for k, v in function_call.function_parameters.items()])
            formatted_function_calls += f"- {function_call_cleaned_string}\n"
        if function_calls:
            idx += 1
    return formatted_function_calls

def get_stored_files(repo_context_manager: RepoContextManager) -> str:
    fetched_files_that_are_stored = list(dict.fromkeys([snippet.file_path for snippet in repo_context_manager.current_top_snippets]))
    joined_files_string = "\n".join(fetched_files_that_are_stored)
    stored_files_string = f'The following files have been stored already. DO NOT CALL THE STORE OR VIEW TOOLS ON THEM AGAIN. \n<stored_files>\n{joined_files_string}\n</stored_files>\n' if fetched_files_that_are_stored else ""
    return stored_files_string

def search_for_context_with_reflection(repo_context_manager: RepoContextManager, reflections_to_read_files: dict[str, tuple[list[str], int]], user_prompt: str, rollout_function_call_histories: list[list[list[AnthropicFunctionCall]]], problem_statement: str) -> tuple[list[Message], list[list[AnthropicFunctionCall]]]:
    try:
        _, function_call_history = perform_rollout(repo_context_manager, reflections_to_read_files, user_prompt)
        rollout_function_call_histories.append(function_call_history)
    except Exception as e:
        logger.error(f"Error in perform_rollout: {e}")
    rollout_stored_files = [snippet.file_path for snippet in repo_context_manager.current_top_snippets]
    # truncated_message_results = message_results[1:] # skip system prompt
    # joined_messages = "\n\n".join([message.content for message in truncated_message_results])
    # overall_score, message_to_contractor = EvaluatorAgent().evaluate_run(
    #     problem_statement=problem_statement, 
    #     run_text=joined_messages,
    #     stored_files=rollout_stored_files,
    # )
    return 0, "", repo_context_manager, rollout_stored_files

def perform_rollout(repo_context_manager: RepoContextManager, reflections_to_gathered_files: dict[str, tuple[list[str], int]], user_prompt: str) -> list[Message]:
    function_call_history = []
    formatted_reflections_prompt = format_reflections(reflections_to_gathered_files)
    updated_user_prompt = user_prompt + formatted_reflections_prompt
    chat_gpt = ChatGPT()
    chat_gpt.messages = [Message(role="system", content=sys_prompt + formatted_reflections_prompt)]
    function_calls_string = chat_gpt.chat_anthropic(
        content=updated_user_prompt,
        stop_sequences=["</function_call>"],
        model=CLAUDE_MODEL,
        message_key="user_request",
        assistant_message_content="<function_call>",
    )
    bad_call_count = 0
    llm_state = {} # persisted across one rollout
    llm_state["function_call_history"] = {}
    for _ in range(MAX_ITERATIONS):
        function_calls = validate_and_parse_function_calls(
            function_calls_string, chat_gpt
        )
        function_outputs = ""
        for function_call in function_calls[:MAX_PARALLEL_FUNCTION_CALLS]:
            function_outputs += handle_function_call(repo_context_manager, function_call, llm_state) + "\n"
            logger.info(f"Function outputs: {function_outputs}")
            logger.info("Function call: " + str(function_call))
            llm_state["function_call_history"] = function_call_history
            if PLAN_SUBMITTED_MESSAGE in function_outputs:
                return chat_gpt.messages, function_call_history
        function_call_history.append(function_calls)
        if len(function_calls) == 0:
            function_outputs = "REMINDER: No function calls were made or your last function call was incorrectly formatted. The correct syntax for function calling is this:\n" \
                + "<function_call>\n<invoke>\n<tool_name>tool_name</tool_name>\n<parameters>\n<param_name>param_value</param_name>\n</parameters>\n</invoke>\n</function_call>" + "\nRemember to gather ALL relevant files. " + get_stored_files(repo_context_manager)
            bad_call_count += 1
        if function_outputs.startswith("FAILURE"):
            bad_call_count += 1
        if bad_call_count >= NUM_BAD_FUNCTION_CALLS:
            return chat_gpt.messages, function_call_history
        if len(function_calls) > MAX_PARALLEL_FUNCTION_CALLS:
            remaining_function_calls = function_calls[MAX_PARALLEL_FUNCTION_CALLS:]
            remaining_function_calls_string = mock_function_calls_to_string(remaining_function_calls)
            function_outputs += "WARNING: You requested more than 1 function call at once. Only the first function call has been processed. The unprocessed function calls were:\n<unprocessed_function_call>\n" + remaining_function_calls_string + "\n</unprocessed_function_call>"
        try:
            function_calls_string = chat_gpt.chat_anthropic(
                content=function_outputs,
                model=CLAUDE_MODEL,
                stop_sequences=["</function_call>"],
                assistant_message_content="<function_call>",
            )
        except Exception as e:
            logger.error(f"Error in chat_anthropic: {e}")
            # return all but the last message because it likely causes an error
            return chat_gpt.messages[:-1], function_call_history
    return chat_gpt.messages, function_call_history

def context_dfs(
    user_prompt: str,
    repo_context_manager: RepoContextManager,
    problem_statement: str,
    num_rollouts: int,
) -> bool | None:
    # initial function call
    reflections_to_read_files = {}
    rollouts_to_scores_and_rcms = {}
    rollout_function_call_histories = []
    for rollout_idx in range(num_rollouts):
        overall_score, message_to_contractor, repo_context_manager, rollout_stored_files = search_for_context_with_reflection(
            repo_context_manager=repo_context_manager,
            reflections_to_read_files=reflections_to_read_files,
            user_prompt=user_prompt,
            rollout_function_call_histories=rollout_function_call_histories,
            problem_statement=problem_statement
        )
        logger.info(f"Completed run {rollout_idx} with score: {overall_score} and reflection: {message_to_contractor}")
        if overall_score is None or message_to_contractor is None:
            continue # can't get any reflections here
        # reflections_to_read_files[message_to_contractor] = rollout_stored_files, overall_score
        rollouts_to_scores_and_rcms[rollout_idx] = (overall_score, repo_context_manager)
        if overall_score >= SCORE_THRESHOLD and len(rollout_stored_files) > STOP_AFTER_SCORE_THRESHOLD_IDX:
            break
    # if we reach here, we have not found a good enough solution
    # select rcm from the best rollout
    logger.info(f"{render_all_attempts(rollout_function_call_histories)}")
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
        snippets = prep_snippets(cloned_repo, query, ticket_progress)
        rcm = get_relevant_context(
            query,
            snippets, # THIS SHOULD BE BROKEN
            ticket_progress,
            chat_logger=ChatLogger({"username": "wwzeng1"}),
        )
        for snippet in rcm.current_top_snippets:
            print(snippet.denotation)
    except Exception as e:
        logger.error(f"context_pruning.py failed to run successfully with error: {e}")
        raise e
