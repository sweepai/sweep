from hmac import new
import json
import re
import time

from attr import dataclass
from loguru import logger
from openai.types.beta.thread import Thread
from openai.types.beta.threads.run import Run

from sweepai.agents.assistant_wrapper import client
from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel, Snippet
from sweepai.core.prompts import system_message_prompt
from sweepai.logn.cache import file_cache
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.prompt_constructor import HumanMessagePrompt
from sweepai.utils.tree_utils import DirectoryTree

ASSISTANT_MAX_CHARS = 4096 * 4 * .95 # ~95% of 4k tokens

class ContextToPrune(RegexMatchableBaseModel):
    paths_to_keep: list[str] = []
    directories_to_expand: list[str] = []

    @classmethod
    def from_string(cls, string: str, **kwargs):
        paths_to_keep = []
        directories_to_expand = []
        paths_to_keep_pattern = (
            r"""<paths_to_keep>(\n)?(?P<paths_to_keep>.*)</paths_to_keep>"""
        )
        paths_to_keep_match = re.search(paths_to_keep_pattern, string, re.DOTALL)
        for path in paths_to_keep_match.groupdict()["paths_to_keep"].split("\n"):
            path = path.strip()
            path = path.replace("* ", "")
            path = path.replace("...", "")
            if len(path) > 1 and " " not in path:
                logger.info(f"paths_to_keep: {path}")
                paths_to_keep.append(path)
        directories_to_expand_pattern = r"""<directories_to_expand>(\n)?(?P<directories_to_expand>.*)</directories_to_expand>"""
        directories_to_expand_match = re.search(
            directories_to_expand_pattern, string, re.DOTALL
        )
        for path in directories_to_expand_match.groupdict()[
            "directories_to_expand"
        ].split("\n"):
            path = path.strip()
            path = path.replace("* ", "")
            path = path.replace("...", "")
            if len(path) > 1 and " " not in path:
                logger.info(f"directories_to_expand: {path}")
                directories_to_expand.append(path)
        return cls(
            paths_to_keep=paths_to_keep,
            directories_to_expand=directories_to_expand,
        )

sys_prompt = """You are a brilliant and meticulous engineer assigned to the following Github issue. We are currently gathering the minimum set of information that allows us to plan the solution to the issue. Take into account the current repository's language, frameworks, and dependencies. It is very important that you get this right.

Reply in the following format:
<contextual_request_analysis>
Use the snippets, issue metadata and other information to determine the information that is critical to solve the issue. For each snippet, identify whether it was a true positive or a false positive.
Propose the most important paths as well as any new paths with a justification.
</contextual_request_analysis>
Use the keep_file_path, add_file_path, and expand_directory tools to optimize the snippets_in_repo, repo_tree, and paths_in_repo until they allow us to perfectly solve the user request."""

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
The above <repo_tree> <snippets_in_repo> and <paths_in_repo> have unnecessary information.
The snippets and paths were fetched by a search engine, so they are noisy.
The unnecessary information will hurt your performance on this task, so modify paths_in_repo, snippets_in_repo, and repo_tree to keep only the absolutely necessary information.

First, list all of the files and directories we should keep in paths_to_keep. Be as specific as you can.
Second, list any directories that are currently closed that should be expanded.
Third, add additional relevant files to the task using the add_file_path tool.
If you expand a directory, we automatically expand all of its subdirectories, so do not list its subdirectories.
Keep all files or directories that are referenced in the issue title or descriptions.
Reply in the following format:
<contextual_request_analysis>
Use the snippets, issue metadata and other information to determine the information that is critical to solve the issue. For each snippet, identify whether it was a true positive or a false positive.
Propose the most important paths as well as any new paths with a justification.
</contextual_request_analysis>
Use the keep_file_path, add_file_path, and expand_directory tools to optimize the snippets_in_repo, repo_tree, and paths_in_repo until they allow us to perfectly solve the user request."""

functions = [
    {
        "name": "keep_file_path",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "File or directory to keep.",
                }
            },
            "required": ["file_path"],
        },
        "description": "Keep an existing file_path that you are certain is relevant to solving the user request. This only works if the file_path is already present in the snippets_in_repo and repo_tree. Unless this is empty, all of the files not listed will be removed from the snippets_in_repo. Make sure to keep ALL of the files that are referenced in the issue title or description.",
    },
    {
        "name": "expand_directory",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {
                    "type": "string",
                    "description": "Directory to expand",
                }
            },
            "required": ["directory_path"],
        },
        "description": "Expand an existing directory that is closed. This is used for exploration only and does not affect the snippets.",
    },
    {
        "name": "add_file_path",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to add to the current snippets.",
                }
            },
            "required": ["file_path"],
        },
        "description": "The most relevant snippet of the file will be added to the current snippets. If the file_path is already present, we will add the next most relevant snippet from the same file_path.",
    },
]

tools = [
    {"type": "function", "function": functions[0]},
    {"type": "function", "function": functions[1]},
    {"type": "function", "function": functions[2]},
]

@staticmethod
def can_add_snippet(snippet: Snippet, current_snippets: list[Snippet]):
    return len(snippet.xml) + sum([len(snippet.xml) for snippet in current_snippets]) <= ASSISTANT_MAX_CHARS

@dataclass
class RepoContextManager:
    dir_obj: DirectoryTree
    current_top_tree: str
    snippets: list[Snippet]
    snippet_scores: dict[str, float]
    current_top_snippets: list[Snippet] = []

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

    def is_path_valid(self, path: str):
        return any(snippet.file_path.startswith(path) for snippet in self.snippets)

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
        snippet_key = lambda snippet: f"{snippet.file_path}:{snippet.start}:{snippet.end}"
        filtered_snippets = [snippet for snippet in self.snippets if snippet.file_path == file_path and snippet not in self.current_top_snippets]
        highest_scoring_snippet = max(
            filtered_snippets,
            key=lambda snippet: self.snippet_scores[snippet_key(snippet)] if snippet_key(snippet) in self.snippet_scores else 0
        )
        return highest_scoring_snippet

    def add_file_paths(self, paths_to_add: list[str]):
        self.dir_obj.add_file_paths(paths_to_add)
        for file_path in paths_to_add:
            highest_scoring_snippet = self.get_highest_scoring_snippet(file_path)
            self.current_top_snippets.append(
                highest_scoring_snippet
            )
            self.current_top_snippets.append(highest_scoring_snippet)


@file_cache()
def get_relevant_context(
    query: str,
    repo_context_manager: RepoContextManager,
):
    modify_iterations: int = 5
    try:
        user_prompt = repo_context_manager.format_context(
            unformatted_user_prompt=unformatted_user_prompt,
            query=query,
        )
        assistant = client.beta.assistants.create(
            name="Relevant Files Assistant",
            instructions=sys_prompt,
            tools=tools,
            model="gpt-4-1106-preview",
        )
        thread = client.beta.threads.create()
        _ = client.beta.threads.messages.create(
            thread.id,
            role="user",
            content=f"Here are the snippets_in_repo, repo_tree, and paths_in_repo:\n{user_prompt}\nUse the keep_file_path, add_file_path, and expand_directory tools to optimize the snippets_in_repo, repo_tree, and paths_in_repo until they allow us to perfectly solve the user request.",
        )
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id,
        )
        done = modify_context(thread, run, repo_context_manager)
        if done:
            return repo_context_manager
        for _ in range(modify_iterations):
            user_prompt = repo_context_manager.format_context(
                unformatted_user_prompt=unformatted_user_prompt, query=query
            )
            _ = client.beta.threads.messages.create(
                thread.id,
                role="user",
                content=f"Here are the new snippets_in_repo, repo_tree, and paths_in_repo:\n{user_prompt}\nUse the keep_file_path, add_file_path, and expand_directory tools to optimize the snippets_in_repo, repo_tree, and paths_in_repo until they allow us to perfectly solve the user request. If the context allows us to perfectly solve the issue(does not require any additional changes), do not use any of the tools.",
            )
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id,
            )
            done = modify_context(thread, run, repo_context_manager)
            messages = client.beta.threads.messages.list(
                thread_id=thread.id,
            )
            current_message = "\n".join(
                [message.content[0].text.value for message in messages.data]
            )
            logger.info(f"Output from OpenAI Assistant: {current_message}")
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
) -> bool | None:
    max_iterations: int = int(
        60 * 10 / 0.25
    )  # 10 minutes divided by 0.25 seconds per iteration
    paths_to_keep = []  # consider persisting these across runs
    paths_to_add = []
    directories_to_expand = []
    logger.info(
        f"Context Management Start:\ncurrent snippet paths: {[snippet.file_path for snippet in repo_context_manager.current_top_snippets]}"
    )
    for _ in range(max_iterations):
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run.status == "completed":
            break
        if (
            run.status != "requires_action"
            or run.required_action is None
            or run.required_action.submit_tool_outputs is None
            or run.required_action.submit_tool_outputs.tool_calls is None
        ):
            time.sleep(0.25)
            continue
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []
        for tool_call in tool_calls:
            try:
                function_input = json.loads(tool_call.function.arguments)
            except:
                logger.warning(
                    f"Could not parse function arguments: {tool_call.function.arguments}"
                )
                continue
            valid_path = repo_context_manager.is_path_valid(function_input["file_path"] if "file_path" in function_input else function_input["directory_path"])
            output = "success" if valid_path else "failure: invalid path"
            if tool_call.function.name == "add_file_path" and valid_path:
                valid_path = valid_path and can_add_snippet(repo_context_manager.get_highest_scoring_snippet(function_input["file_path"]), repo_context_manager.current_top_snippets)
                paths_to_add.append(function_input["file_path"])
                output = "success" if valid_path else "failure: no space left, current snippets are too long"
            tool_outputs.append(
                {
                    "tool_call_id": tool_call.id,
                    "output": output,
                }
            )
            if valid_path:
                if tool_call.function.name == "keep_file_path":
                    paths_to_keep.append(function_input["file_path"])
                elif tool_call.function.name == "expand_directory":
                    directories_to_expand.append(function_input["directory_path"])
        run = client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread.id,
            run_id=run.id,
            tool_outputs=tool_outputs,
        )
    logger.info(f"Context Management End:\npaths_to_keep: {paths_to_keep}\npaths_to_add: {paths_to_add}\ndirectories_to_expand: {directories_to_expand}")
    if paths_to_keep: repo_context_manager.remove_all_non_kept_paths(paths_to_keep)
    if directories_to_expand: repo_context_manager.expand_all_directories(directories_to_expand)
    return not (paths_to_keep or directories_to_expand or paths_to_add)


if __name__ == "__main__":
    import os

    from sweepai.utils.ticket_utils import prep_snippets

    installation_id = os.environ["INSTALLATION_ID"]
    cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")
    query = "Delete the is_python_issue logic from the ticket file. Move this logic to sweep_bot.py's files to change method. Also change this in on_comment. Finally update the readme.md."
    repo_context_manager = prep_snippets(cloned_repo, query)
    rcm = get_relevant_context(query, repo_context_manager)
    import pdb

    pdb.set_trace()
