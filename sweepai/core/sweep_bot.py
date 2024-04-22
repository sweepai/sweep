import base64
import copy
import re
import traceback
from typing import Dict, Generator

from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from loguru import logger
from networkx import Graph
from pydantic import BaseModel

from sweepai.agents.modify import validate_and_parse_function_call
from sweepai.agents.modify_file import modify_file
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.annotate_code_openai import get_annotated_source_code
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import (
    AssistantRaisedException,
    FileChangeRequest,
    MaxTokensExceeded,
    Message,
    NoFilesException,
    ProposedIssue,
    PullRequest,
    RegexMatchError,
    SandboxResponse,
    Snippet,
)
from sweepai.core.prompts import (
    files_to_change_prompt,
    context_files_to_change_prompt,
    pull_request_prompt,
    subissues_prompt,
    files_to_change_system_prompt,
    plan_review_prompt,
    planning_tools_for_eval,
    planning_tools_prompt,
    planning_redo_prompt
)
from sweepai.utils.chat_logger import ChatLogger, discord_log_error
from sweepai.utils.convert_openai_anthropic import AnthropicFunctionCall
from sweepai.utils.progress import (
    AssistantAPIMessage,
    AssistantConversation,
    TicketProgress,
)
from sweepai.utils.str_utils import get_hash
from sweepai.utils.utils import check_syntax
from sweepai.utils.github_utils import ClonedRepo, commit_multi_file_changes

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"
MODEL = "claude-3-opus-20240229"

NO_FUNCTION_CALL = """ERROR!\n\nNo function call was made. If you attempted to make a function call but failed retry again but with the correct xml format.
If you are finished with fixing the issues with the plan you can submit the final plan by using the `submit_final_plan` tool.
An example is given below:
<function_call>
<invoke>
<parameters>
<submit_final_plan>
<explanation>
[Explanation of why this plan was chosen, what issues were fixed (if any) and how it solves the original problem]
</explanation>
<final_plan>
<modify file="example.py">
[Example instructions here]
</modify>
...
<modify file="anotherexamplefile.py">
[More example instructions here]
</modify>
[Your explanation of why this plan was chosen and how it aligns with the guidelines and any modications made to this plan]
</final_plan>
</submit_final_plan>
</parameters>
</invoke>
</function_call>
"""


def to_raw_string(s):
    return repr(s).lstrip("u")[1:-1]


sandbox_error_prompt = """The following error logs were returned from `{command}`. Make changes to the current file so that it passes this CI/CD command.

```
{error_logs}
```

Edit old_code to pass the CI/CD."""

sandbox_error_prompt_test = """The following error logs were returned from `{command}`. Make changes to the current file so that it passes this CI/CD command.

```
{error_logs}
```

Edit old_code to pass the CI/CD.
1. Analyze the business logic and tests. Identify whether the failure is in the unit tests or business logic.
2a. If the business logic is correct fix the test to return the expected output.
2b. If the business logic has a bug or you are unsure, skip the failing tests with an explanation."""

def safe_decode(
    repo: Repository,
    path: str,
    *args,
    **kwargs
):
    """
    By default, this function will decode the file contents from the repo.
    But if the file > 1MB, we will fetch the raw content and then decode it manually ourselves.
    It's a strange bug that occurs when the file is too large and the GitHub API doesn't decode it properly and returns encoding="none".
    Reference: https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28#get-repository-content
    """
    contents = repo.get_contents(path, *args, **kwargs)
    if contents.encoding == "none":
        blob = repo.get_git_blob(contents.sha)
        # this might be more correct but chatgpt said the latter is better
        # return base64.b64decode(bytearray(blob.content, "utf-8")).decode("utf-8")
        return base64.b64decode(blob.content).decode("utf-8")
    return contents.decoded_content.decode("utf-8")

def remove_line_numbers(s: str) -> str:
    # Check if more than 50% of lines have line numbers
    # Remove line numbers with spaces after (e.g. "1: {code}")
    if len(re.findall(r"\d+?: ", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?: ", "", s, flags=re.MULTILINE)

    # Remove line numbers with no space after (e.g. "112:{code}")
    if len(re.findall(r"\d+?:", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?:", "", s, flags=re.MULTILINE)
    return s


def is_blocked(file_path: str, blocked_dirs: list[str]):
    for blocked_dir in blocked_dirs:
        if file_path.startswith(blocked_dir) and len(blocked_dir) > 0:
            return {"success": True, "path": blocked_dir}
    return {"success": False}

def validate_file_change_requests(
    file_change_requests: list[FileChangeRequest],
    cloned_repo: ClonedRepo,
):
    # TODO: add better suffixing
    for fcr in file_change_requests:
        if fcr.change_type == "modify":
            try:
                cloned_repo.get_file_contents(fcr.filename)
            except FileNotFoundError as e:
                logger.warning(f"Failed to get file contents for {fcr.filename} due to {e}, trying prefixes")
                for file_path in cloned_repo.get_file_list():
                    if file_path.endswith(fcr.filename):
                        logger.info(f"Found similar file {fcr.filename} at {file_path}")
                        cloned_repo.get_file_contents(file_path)
                        fcr.filename = file_path
                        break
                else:
                    fcr.change_type = "create" # need better handling
        elif fcr.change_type == "create":
            try:
                cloned_repo.get_file_contents(fcr.filename)
                fcr.change_type = "modify" # need better handling
            except FileNotFoundError:
                pass
        
def sort_and_fuse_snippets(
    snippets: list[Snippet],
    fuse_distance: int = 600,
) -> list[Snippet]:
    if len(snippets) <= 1:
        return snippets
    new_snippets = []
    snippets.sort(key=lambda x: x.start)
    current_snippet = snippets[0]
    for snippet in snippets[1:]:
        if current_snippet.end + fuse_distance >= snippet.start:
            current_snippet.end = max(current_snippet.end, snippet.end)
        else:
            new_snippets.append(current_snippet)
            current_snippet = snippet
    new_snippets.append(current_snippet)
    return new_snippets
    
def organize_snippets(snippets: list[Snippet], fuse_distance: int=600) -> list[Snippet]:
    """
    Fuse and dedup snippets that are contiguous. Combine ones of same file.
    """
    fused_snippets = []
    added_file_paths = set()
    for i, snippet in enumerate(snippets):
        if snippet.file_path in added_file_paths:
            continue
        added_file_paths.add(snippet.file_path)
        current_snippets = [snippet]
        for current_snippet in snippets[i + 1:]:
            if snippet.file_path == current_snippet.file_path:
                current_snippets.append(current_snippet)
        current_snippets = sort_and_fuse_snippets(current_snippets, fuse_distance=fuse_distance)
        fused_snippets.extend(current_snippets)
    return fused_snippets

def get_max_snippets(
    snippets: list[Snippet],
    budget: int = 150_000 * 3.5, # 140k tokens
    expand: int = 3000, # testing expand
):
    """
    Start with max number of snippets and then remove then until the budget is met.
    Return the resulting organized snippets.
    """
    for i in range(len(snippets), 0, -1):
        proposed_snippets = organize_snippets(snippets[:i])
        cost = sum([len(snippet.expand(expand * 2).get_snippet(False, False)) for snippet in proposed_snippets])
        if cost <= budget:
            return proposed_snippets
    raise Exception("Budget number of chars too low!")

def parse_xml_tag_from_string(tag: str, string: str) -> str:
    match = re.search(f"<{tag}>(.*?)</{tag}>", string, re.DOTALL)
    return match.group(1) if match else None

# handles function calls made by planning
def handle_planning_function_call(
        function_call: AnthropicFunctionCall, 
        llm_state: dict[str, str | bool | list[str]],
        cloned_repo: ClonedRepo):
    tool_name = function_call.function_name
    tool_call = function_call.function_parameters
    if tool_name == "submit_final_plan":
        llm_state["done"] = True
        final_plan = tool_call["final_plan"].strip("\n")
        return final_plan, llm_state
    elif tool_name == "view_file":
        file_path = tool_call["file_name"].strip() # strip ALL whitespace
        try:
            file_contents = cloned_repo.get_file_contents(file_path)
            success_message = f'SUCCESS!\n\nFile {file_path} found in the codebase. Here are the contents:\n\n<file name="{file_path}">\n{file_contents}\n</file>'
            return success_message, llm_state
        except FileNotFoundError:
            import pdb; pdb.set_trace()
            error_message = f"ERROR!\n\nFile {file_path} not found in the codebase."
            return error_message, llm_state
    else:
        available_tools = ", ".join(llm_state["available_tools"])
        error_message = f"ERROR!\n\nUnknown tool {tool_name}:\n\nYou have access to the following tools only:\n{available_tools}\n\nMake sure you respond with the correct xml format."
        return error_message, llm_state

# iterate on the initial plan to improve it using an agent
def iterate_on_plan(chat_gpt: ChatGPT, cloned_repo: ClonedRepo, chat_logger: ChatLogger = None):
    # keep track of state
    llm_state = {
        "done": False,
        "available_tools": ["view_file", "submit_final_plan"]
    }
    # make initial function call
    planning_tools_prompt_string = planning_tools_prompt
    # give agent what tools it has available
    for tool in llm_state["available_tools"]:
        planning_tools_prompt_string += f'\n\n{planning_tools_for_eval[tool]}'
    function_calls_string = chat_gpt.chat_anthropic(
        content=planning_tools_prompt_string,
        model=MODEL,
        stop_sequences=["</function_call>"],
        temperature=0.1
    )
    final_plan = ""
    # max 10 iterations anymore probably means something has gone wrong.
    max_iterations = 10
    for i in range(max_iterations):
        function_call = validate_and_parse_function_call(function_calls_string, chat_gpt)
        if function_call:
            function_output, llm_state = handle_planning_function_call(function_call, llm_state, cloned_repo)
            # check if we are done
            if llm_state["done"]:
                # update chat logger
                if chat_logger:
                    chat_logger.add_chat(
                        {
                            "model": MODEL,
                            "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                            "output": f"We are done! Here is the final output:\n\n{function_output}",
                        }
                    )
                final_plan = function_output
                break
            # get the next function call
            function_calls_string = chat_gpt.chat_anthropic(
                content=function_output,
                model=MODEL,
                stop_sequences=["</function_call>"],
                temperature=0.1
            )
        else:
            # get the next function call
            function_calls_string = chat_gpt.chat_anthropic(
                content=NO_FUNCTION_CALL,
                model=MODEL,
                stop_sequences=["</function_call>"],
                temperature=0.1
            )

        if chat_logger:
            output_message = function_call
            if i == max_iterations - 1:
                output_message += f"\n\nMAX ITERATIONS REACHED!"

            chat_logger.add_chat(
                {
                    "model": MODEL,
                    "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                    "output": output_message,
                }
            )
    return final_plan

# parse the output of the evaluation of the planning
def parse_planning_evaluation(evaluation: str) -> tuple[list[str], bool]:
    initial_plan_is_good = parse_xml_tag_from_string("initial_plan_is_good", evaluation)
    code_files_to_fetch = parse_xml_tag_from_string("code_files_to_fetch", evaluation)
    initial_plan_is_good = False if initial_plan_is_good and 'no' in initial_plan_is_good else True # default to True if no tag is found
    code_files_to_fetch = [file.strip() for file in code_files_to_fetch.split(",")] if code_files_to_fetch and code_files_to_fetch.strip() else [] # default to empty list if no tag is found
    return code_files_to_fetch, initial_plan_is_good

def planning_qc_pipeline(chat_gpt: ChatGPT, cloned_repo: ClonedRepo, chat_logger: ChatLogger = None):
    # get initial evaluation
    initial_evaluation = chat_gpt.chat_anthropic(
        content=plan_review_prompt,
        model=MODEL,
        temperature=0.1
    )

    if chat_logger:
        chat_logger.add_chat(
            {
                "model": MODEL,
                "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                "output": initial_evaluation,
            })
    # based on results of evaluation, iterate on the plan
    # first parse the initial evaluation to see if there are any code files we need to fetch
    code_files_to_fetch, initial_plan_is_good = parse_planning_evaluation(initial_evaluation)
    if initial_plan_is_good:
        return "" # return if no fixes are needed
    fetched_code_files = {}
    for code_file in code_files_to_fetch:
        try:
            fetched_code_file = cloned_repo.get_file_contents(code_file)
            fetched_code_files[code_file] = fetched_code_file
        except FileNotFoundError:
            pass
    formatted_code_files = ""
    for code_file, fetched_code_file in fetched_code_files.items():
        formatted_code_files += f'\n<code_file name="{code_file}">\n{fetched_code_file}\n</code_file>\n'
    # now we get a new plan
    formatted_planning_redo_prompt = planning_redo_prompt.format(code_files=formatted_code_files)
    final_plan = chat_gpt.chat_anthropic(
        content=formatted_planning_redo_prompt,
        model=MODEL,
        temperature=0.1
    )
    if chat_logger:
        chat_logger.add_chat(
            {
                "model": MODEL,
                "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                "output": final_plan,
            })
    return final_plan

# get the plan and fcrs for the change
def get_files_to_change(
    relevant_snippets: list[Snippet],
    read_only_snippets: list[Snippet],
    problem_statement,
    repo_name,
    cloned_repo: ClonedRepo,
    import_graph: Graph | None = None,
    pr_diffs: str = "",
    chat_logger: ChatLogger = None,
    seed: int = 0,
    context: bool = False,
) -> tuple[list[FileChangeRequest], str]:
    assert len(relevant_snippets) > 0
    file_change_requests: list[FileChangeRequest] = []
    messages: list[Message] = []
    messages.append(
        Message(role="system", content=files_to_change_system_prompt, key="system")
    )

    interleaved_snippets = []
    for i in range(max(len(relevant_snippets), len(read_only_snippets))):
        if i < len(relevant_snippets):
            interleaved_snippets.append(relevant_snippets[i])
        if i < len(read_only_snippets):
            interleaved_snippets.append(read_only_snippets[i])

    interleaved_snippets = relevant_snippets

    max_snippets = get_max_snippets(interleaved_snippets)
    relevant_snippets = [snippet for snippet in max_snippets if any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]
    read_only_snippets = [snippet for snippet in max_snippets if not any(snippet.file_path == relevant_snippet.file_path for relevant_snippet in relevant_snippets)]

    relevant_snippet_template = '<relevant_file index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</relevant_file>'
    read_only_snippet_template = '<read_only_snippet index="{i}">\n<file_path>\n{file_path}\n</file_path>\n<source>\n{content}\n</source>\n</read_only_snippet>'
    # attach all relevant snippets
    if not context:
        formatted_relevant_snippets = []
        for i, snippet in enumerate(relevant_snippets):
            annotated_source_code, code_summaries = get_annotated_source_code(
                source_code=snippet.get_snippet(add_lines=False),
                issue_text=problem_statement,
                file_path=snippet.file_path,
            )
            formatted_relevant_snippets.append(
                relevant_snippet_template.format(
                    i=i,
                    file_path=snippet.file_path,
                    content=annotated_source_code,
                )
            )
            # cohere_rerank_response = cohere_rerank_call(
            #     query=problem_statement,
            #     documents=code_summaries,
            # )
        joined_relevant_snippets = "\n".join(
            formatted_relevant_snippets
        )
    else:
        joined_relevant_snippets = "\n".join(
            relevant_snippet_template.format(
                i=i,
                file_path=snippet.file_path,
                content=snippet.expand(300).get_snippet(add_lines=False),
            ) for i, snippet in enumerate(relevant_snippets)
        )
    relevant_snippets_message = f"# Relevant codebase files:\nHere are the relevant files from the codebase. We previously summarized each of the files to help you solve the GitHub issue. These will be your primary reference to solve the problem:\n\n<relevant_files>\n{joined_relevant_snippets}\n</relevant_files>"
    messages.append(
        Message(
            role="user",
            content=relevant_snippets_message,
            key="relevant_code_files",
        )
    )
    joined_relevant_read_only_snippets = "\n".join(
        read_only_snippet_template.format(
            i=i,
            file_path=snippet.file_path,
            content=snippet.get_snippet(add_lines=False),
        ) for i, snippet in enumerate(read_only_snippets)
    )
    read_only_snippets_message = f"<relevant_read_only_snippets>\n{joined_relevant_read_only_snippets}\n</relevant_read_only_snippets>"
    if read_only_snippets:
        messages.append(
            Message(
                role="user",
                content=read_only_snippets_message,
                key="relevant_snippets",
            )
        )

    # if import_graph: # no evidence this helps
    #     sub_graph = import_graph.subgraph(
    #         [snippet.file_path for snippet in relevant_snippets + read_only_snippets]
    #     )
    #     import_graph = generate_import_graph_text(sub_graph).strip("\n")
    #     # serialize the graph so LLM can read it
    #     if len(import_graph.splitlines()) > 5 and "──>" in import_graph:
    #         graph_text = f"<graph_text>\nThis represents the file-to-file import graph, where each file is listed along with its imported files using arrows (──>) to show the directionality of the imports. Indentation is used to indicate the hierarchy of imports, and files that are not importing any other files are listed separately at the bottom.\n{import_graph}\n</graph_text>"

    #         messages.append(
    #             Message(
    #                 role="user",
    #                 content=graph_text,
    #                 key="graph_text",
    #             )
    #         )
    # previous_diffs = get_previous_diffs(
    #     problem_statement,
    #     cloned_repo=cloned_repo,
    #     relevant_file_paths=[snippet.file_path for snippet in relevant_snippets],
    # )
    # messages.append( # temporarily disable in main
    #     Message(
    #         role="user",
    #         content=previous_diffs,
    #     )
    # )
    messages.append(
        Message(
            role="user",
            content=f"# GitHub Issue\n<issue>\n{problem_statement}\n</issue>",
        )
    )
    if pr_diffs:
        messages.append(
            Message(role="user", content=pr_diffs, key="pr_diffs")
        )
    try:
        print("messages")
        for message in messages:
            print(message.content + "\n\n")
        joint_message = "\n\n".join(message.content for message in messages[1:])
        print("messages", joint_message)
        chat_gpt = ChatGPT(
            messages=[
                Message(
                    role="system",
                    content=files_to_change_system_prompt,
                ),
            ],
        )
        # get initial plan
        files_to_change_response = chat_gpt.chat_anthropic(
            content=joint_message + "\n\n" + (files_to_change_prompt if not context else context_files_to_change_prompt),
            model=MODEL,
            temperature=0.1
        )
        
        final_plan = planning_qc_pipeline(chat_gpt, cloned_repo, chat_logger=chat_logger)
        if final_plan:
            files_to_change_response = final_plan # update our final plan

        # files_to_change_response = iterate_on_plan(chat_gpt, cloned_repo, chat_logger=chat_logger)
        if chat_logger:
            chat_logger.add_chat(
                {
                    "model": MODEL,
                    "messages": [{"role": message.role, "content": message.content} for message in chat_gpt.messages],
                    "output": files_to_change_response,
                })
        print("files_to_change_response", files_to_change_response)
        relevant_modules = []
        pattern = re.compile(r"<relevant_modules>(.*?)</relevant_modules>", re.DOTALL)
        relevant_modules_match = pattern.search(files_to_change_response)
        if relevant_modules_match:
            relevant_modules = [relevant_module.strip() for relevant_module in relevant_modules_match.group(1).split("\n") if relevant_module.strip()]
        print("relevant_modules", relevant_modules)
        file_change_requests = []
        for re_match in re.finditer(
            FileChangeRequest._regex, files_to_change_response, re.DOTALL
        ):
            file_change_request = FileChangeRequest.from_string(re_match.group(0))
            file_change_request.raw_relevant_files = " ".join(relevant_modules)
            file_change_requests.append(file_change_request)
        return file_change_requests, files_to_change_response
    except RegexMatchError as e:
        print("RegexMatchError", e)

    return [], ""


class CodeGenBot(ChatGPT):
    def generate_subissues(self, retries: int = 3):
        subissues: list[ProposedIssue] = []
        for count in range(retries):
            try:
                logger.info(f"Generating for the {count}th time...")
                files_to_change_response = self.chat(
                    subissues_prompt, message_key="subissues"
                )  # Dedup files to change here
                subissues = []
                for re_match in re.finditer(
                    ProposedIssue._regex, files_to_change_response, re.DOTALL
                ):
                    subissues.append(ProposedIssue.from_string(re_match.group(0)))
                if subissues:
                    return subissues
            except RegexMatchError:
                logger.warning("Failed to parse! Retrying...")
                self.delete_messages_from_chat("files_to_change")
                continue
        raise NoFilesException()

    def get_files_to_change(
        self, retries=1, pr_diffs: str | None = None
    ) -> tuple[list[FileChangeRequest], str]:
        raise DeprecationWarning("This function is deprecated. Use get_files_to_change instead.")
        file_change_requests: list[FileChangeRequest] = []
        try:
            if pr_diffs is not None:
                self.delete_messages_from_chat("pr_diffs")
                self.messages.insert(
                    1, Message(role="user", content=pr_diffs, key="pr_diffs")
                )

            # pylint: disable=no-member
            # pylint: disable=access-member-before-definition
            if hasattr(self, "ticket_progress") and self.ticket_progress is not None:
                self.ticket_progress: TicketProgress = self.ticket_progress
                self.ticket_progress.planning_progress.assistant_conversation.messages = (
                    []
                )
                for message in self.messages:
                    self.ticket_progress.planning_progress.assistant_conversation.messages.append(
                        AssistantAPIMessage(
                            content=message.content,
                            role=message.role,
                        )
                    )
                self.ticket_progress.planning_progress.assistant_conversation.messages.append(
                    AssistantAPIMessage(
                        content=files_to_change_prompt,
                        role="user",
                    )
                )
                self.ticket_progress.save()
            old_system_prompt = self.messages[0].content
            self.messages[0].content = files_to_change_system_prompt
            # pylint: enable=no-member
            # pylint: enable=access-member-before-definition
            try:
                files_to_change_response = self.chat_anthropic(
                    files_to_change_prompt, message_key="files_to_change", model="claude-3-opus-20240229"
                )
            except Exception:
                files_to_change_response = self.chat(
                    files_to_change_prompt, message_key="files_to_change"
                )
            self.messages[0].content = old_system_prompt
            if self.ticket_progress is not None:
                self.ticket_progress.planning_progress.assistant_conversation.messages.append(
                    AssistantAPIMessage(
                        content=files_to_change_response, role="assistant"
                    )
                )
                self.ticket_progress.save()
            file_change_requests = []
            for re_match in re.finditer(
                FileChangeRequest._regex, files_to_change_response, re.DOTALL
            ):
                file_change_request = FileChangeRequest.from_string(re_match.group(0))
                file_change_requests.append(file_change_request)
            if file_change_requests:
                plan_str = "\n".join(
                    [fcr.instructions_display for fcr in file_change_requests]
                )
                return file_change_requests, plan_str
        except RegexMatchError as e:
            logger.info(f"{e}")
            logger.warning("Failed to parse! Retrying...")
            self.delete_messages_from_chat("files_to_change")
            self.delete_messages_from_chat("pr_diffs")

        raise NoFilesException()

    def generate_pull_request(self, retries=2) -> PullRequest:
        for count in range(retries):
            too_long = False
            try:
                logger.info(f"Generating for the {count}th time...")
                if (
                    too_long or count >= retries - 1
                ):  # if on last try, use gpt4-32k (improved context window)
                    pr_text_response = self.chat(
                        pull_request_prompt,
                        message_key="pull_request",
                        model=DEFAULT_GPT35_MODEL,
                    )
                else:
                    pr_text_response = self.chat(
                        pull_request_prompt,
                        message_key="pull_request",
                        model=DEFAULT_GPT4_32K_MODEL,
                    )

                # Add triple quotes if not present
                if not pr_text_response.strip().endswith('"""'):
                    pr_text_response += '"""'

                self.messages = self.messages[:-2]
            except SystemExit:
                raise SystemExit
            except Exception as e:
                e_str = str(e)
                if "too long" in e_str:
                    too_long = True
                logger.warning(f"Exception {e_str}. Failed to parse! Retrying...")
                self.messages = self.messages[:-1]
                continue
            pull_request = PullRequest.from_string(pr_text_response)

            final_branch = pull_request.branch_name[:240]
            final_branch = final_branch.split("/", 1)[-1]

            use_underscores = get_branch_name_config(self.repo)
            if use_underscores:
                final_branch = final_branch.replace("/", "_")

            pull_request.branch_name = (
                "sweep/" if not use_underscores else "sweep_"
            ) + final_branch
            return pull_request
        raise Exception("Could not generate PR text")


class GithubBot(BaseModel):
    class Config:
        arbitrary_types_allowed = True  # for repo: Repository

    repo: Repository

    def get_contents(self, path: str, branch: str = ""):
        if not branch:
            branch = SweepConfig.get_branch(self.repo)
        try:
            return self.repo.get_contents(path, ref=branch)
        except Exception as e:
            logger.warning(path)
            raise e

    def get_file(self, file_path: str, branch: str = "") -> ContentFile:
        content = self.get_contents(file_path, branch)
        assert not isinstance(content, list)
        return content

    def check_path_exists(self, path: str, branch: str = ""):
        try:
            self.get_contents(path, branch)
            return True
        except SystemExit:
            raise SystemExit
        except Exception:
            return False

    def clean_branch_name(self, branch: str) -> str:
        branch = re.sub(r"[^a-zA-Z0-9_\-/]", "_", branch)
        branch = re.sub(r"_+", "_", branch)
        branch = branch.strip("_")

        return branch

    def create_branch(self, branch: str, base_branch: str = None, retry=True) -> str:
        # Generate PR if nothing is supplied maybe
        branch = self.clean_branch_name(branch)
        base_branch = self.repo.get_branch(
            base_branch if base_branch else SweepConfig.get_branch(self.repo)
        )
        try:
            try:
                test = self.repo.get_branch("sweep")
                assert test is not None
                # If it does exist, fix
                branch = branch.replace(
                    "/", "_"
                )  # Replace sweep/ with sweep_ (temp fix)
            except Exception:
                pass

            self.repo.create_git_ref(f"refs/heads/{branch}", base_branch.commit.sha)
            return branch
        except GithubException as e:
            logger.error(f"Error: {e}, trying with other branch names...")
            logger.warning(
                f"{branch}\n{base_branch}, {base_branch.name}\n{base_branch.commit.sha}"
            )
            if retry:
                for i in range(1, 10):
                    try:
                        logger.warning(f"Retrying {branch}_{i}...")
                        _hash = get_hash()[:5]
                        self.repo.create_git_ref(
                            f"refs/heads/{branch}_{_hash}", base_branch.commit.sha
                        )
                        return f"{branch}_{_hash}"
                    except GithubException:
                        pass
            else:
                new_branch = self.repo.get_branch(branch)
                if new_branch:
                    return new_branch.name
            discord_log_error(
                f"Error: {e}, could not create branch name {branch} on {self.repo.full_name}"
            )
            raise e

    def populate_snippets(self, snippets: list[Snippet]):
        for snippet in snippets:
            try:
                snippet.content = safe_decode(
                    self.repo,
                    snippet.file_path,
                    ref=SweepConfig.get_branch(self.repo)
                )
                snippet.start = max(1, snippet.start)
                snippet.end = min(len(snippet.content.split("\n")), snippet.end)
            except SystemExit:
                raise SystemExit
            except Exception:
                logger.error(snippet)

    def validate_file_change_requests(
        self, file_change_requests: list[FileChangeRequest], branch: str = ""
    ):
        blocked_dirs = get_blocked_dirs(self.repo)
        created_files = []
        for file_change_request in file_change_requests:
            try:
                contents = None
                try:
                    contents = self.repo.get_contents(
                        file_change_request.filename,
                        branch or SweepConfig.get_branch(self.repo),
                    )
                except UnknownObjectException:
                    for prefix in [
                        self.repo.full_name,
                        self.repo.owner.login,
                        self.repo.name,
                    ]:
                        try:
                            new_filename = file_change_request.filename.replace(
                                prefix + "/", "", 1
                            )
                            contents = self.repo.get_contents(
                                new_filename,
                                branch or SweepConfig.get_branch(self.repo),
                            )
                            file_change_request.filename = new_filename
                            break
                        except UnknownObjectException:
                            pass
                    else:
                        contents = None
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.error(f"FileChange Validation Error: {e}")

                if (
                    contents or file_change_request.filename in created_files
                ) and file_change_request.change_type == "create":
                    file_change_request.change_type = "modify"
                elif (
                    not (contents or file_change_request.filename in created_files)
                    and file_change_request.change_type == "modify"
                ):
                    file_change_request.change_type = "create"
                
                if contents is not None:
                    try:
                        file_change_request.old_content = safe_decode(self.repo, file_change_request.filename, ref=SweepConfig.get_branch(self.repo))
                    except Exception as e:
                        logger.info(f"Error: {e}")
                        file_change_request.old_content = ""

                created_files.append(file_change_request.filename)

                block_status = is_blocked(file_change_request.filename, blocked_dirs)
                if block_status["success"]:
                    # red X emoji
                    file_change_request.instructions = (
                        f'❌ Unable to modify files in `{block_status["path"]}`\nEdit'
                        " `sweep.yaml` to configure."
                    )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.info(traceback.format_exc())
                raise e
        file_change_requests = [
            file_change_request for file_change_request in file_change_requests
        ]
        return file_change_requests


ASSET_BRANCH_NAME = "sweep/assets"


class SweepBot(CodeGenBot, GithubBot):
    comment_pr_diff_str: str | None = None
    comment_pr_files_modified: Dict[str, str] | None = None
    ticket_progress: TicketProgress | None = None

    def validate_sandbox(self, file_change_requests: list[FileChangeRequest]):
        # if all are successful return the first one, otherwise return dummy one
        fcr_file_paths = [
            fcr.filename for fcr in file_change_requests if fcr.change_type == "modify"
        ]
        sandbox_responses: list[SandboxResponse] = []
        for fcr_file_path in fcr_file_paths:
            try:
                contents = safe_decode(
                    self.repo,
                    fcr_file_path,
                    ref=SweepConfig.get_branch(self.repo)
                )
                _, sandbox_response = self.check_sandbox(fcr_file_path, contents)
                sandbox_responses.append(sandbox_response)
            except Exception as e:
                logger.error(f"Error: {e}")
        if sandbox_responses and all(
            sandbox_response.success for sandbox_response in sandbox_responses
        ):
            return sandbox_responses[0], fcr_file_paths[0]
        return None, None

    def validate_file_change_requests(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str = "",
    ):
        file_change_requests = super().validate_file_change_requests(
            file_change_requests, branch
        )
        return file_change_requests

    def init_asset_branch(
        self,
        branch: str = ASSET_BRANCH_NAME,
    ):
        try:
            self.repo.get_branch(branch)
            return
        except GithubException:
            self.repo.create_git_ref(
                f"refs/heads/{branch}",
                self.repo.get_branch(self.repo.default_branch).commit.sha,
            )

    def check_completion(self, file_name: str, new_content: str) -> bool:
        return True

    def check_sandbox(
        self,
        file_path: str,
        content: str,
        check: list[str] = [],
    ):
        sandbox_execution: SandboxResponse | None = None
        is_valid_syntax, error_message = check_syntax(file_path, content)
        output_message = f"Checking {file_path} for syntax errors...\n" + (
            f"✅ {file_path} has no syntax errors!"
            if is_valid_syntax
            else f"❌ {file_path} has syntax errors:\n{error_message}"
        )
        sandbox_execution = {
            "success": is_valid_syntax,
            "error_messages": [error_message],
            "outputs": [output_message],
            "updated_content": content,
        }
        sandbox_execution = SandboxResponse(**sandbox_execution)
        return content, sandbox_execution



    def modify_file(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str = None,
        assistant_conversation: AssistantConversation | None = None,
        additional_messages: list[Message] = [],
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] = None,
    ):
        new_files = modify_file(
            self.cloned_repo,
            self.human_message.get_issue_request(),
            self.human_message.get_issue_metadata(),
            file_change_requests,
            branch,
            self.comment_pr_diff_str,
            assistant_conversation,
            self.ticket_progress,
            self.chat_logger,
            additional_messages=additional_messages,
            previous_modify_files_dict=previous_modify_files_dict,
        )

        commit_message = f"feat: Updated {len(new_files or [])} files"[:50]
        return new_files, commit_message

    def change_files_in_github_iterator(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str,
        blocked_dirs: list[str],
        additional_messages: list[Message] = []
    ) -> Generator[tuple[FileChangeRequest, bool], None, None]:
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] | None = None
        additional_messages_copy = copy.deepcopy(additional_messages)
        (
            changed_file,
            commit,
            new_file_contents
        ) = self.handle_modify_file_main(
            branch=branch,
            assistant_conversation=None,
            additional_messages=additional_messages_copy,
            previous_modify_files_dict=previous_modify_files_dict,
            file_change_requests=file_change_requests
        )
        # update previous_modify_files_dict
        if not previous_modify_files_dict:
            previous_modify_files_dict = {}
        if new_file_contents:
            for file_name, file_content in new_file_contents.items():
                previous_modify_files_dict[file_name] = file_content
                # update status of corresponding fcr to be succeeded
                for file_change_request in file_change_requests:
                    if file_change_request.filename == file_name:
                        file_change_request.status = "succeeded"
        # set all fcrs without a corresponding change to be failed
        for file_change_request in file_change_requests:
            if file_change_request.status != "succeeded":
                file_change_request.status = "failed"
            # also update all commit hashes associated with the fcr
            file_change_request.commit_hash_url = commit.html_url if commit else None

        yield (
            new_file_contents,
            changed_file,
            commit,
            file_change_requests,
        )

    def handle_modify_file_main(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str,
        assistant_conversation: AssistantConversation | None = None,
        additional_messages: list[Message] = [],
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] = None,
    ): # this is enough to make changes to a branch
        commit_message: str = None
        try:
            try:
                (
                    new_file_contents,
                    suggested_commit_message,
                ) = self.modify_file(
                    file_change_requests,
                    assistant_conversation=assistant_conversation,
                    additional_messages=additional_messages,
                    previous_modify_files_dict=previous_modify_files_dict,
                )
                commit_message = suggested_commit_message
            except Exception as e:
                logger.error(e)
                raise e

            # If no files were updated, log a warning and return
            if not new_file_contents:
                logger.warning(
                    "No changes made to any file!"
                )
                return (
                    False,
                    None,
                    new_file_contents
                )
            try:
                new_file_contents_to_commit = {file_path: file_data["contents"] for file_path, file_data in new_file_contents.items()}
                result = commit_multi_file_changes(self.repo, new_file_contents_to_commit, commit_message, branch)
            except AssistantRaisedException as e:
                raise e
            except Exception as e:
                logger.info(f"Error in updating file, repulling and trying again {e}")
                # file = self.get_file(file_change_request.filename, branch=branch)
                # result = self.repo.update_file(
                #     file_name,
                #     commit_message,
                #     new_file_contents,
                #     file.sha,
                #     branch=branch,
                # )
                raise e
            return True, result, new_file_contents
        except (MaxTokensExceeded, AssistantRaisedException) as e:
            raise e
        except Exception:
            tb = traceback.format_exc()
            logger.info(f"Error in handle_modify_file: {tb}")
            return False, None, {}
