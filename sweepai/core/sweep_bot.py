from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import field
import traceback
import re
import requests
from typing import Generator, Any, Dict, List, Tuple
from logn import logger

from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from github.Commit import Commit
from pydantic import BaseModel
from sweepai.agents.graph_child import GraphChildBot, GraphContextAndPlan
from sweepai.agents.graph_parent import GraphParentBot

from sweepai.core.chat import ChatGPT
from sweepai.core.edit_chunk import EditBot
from sweepai.core.entities import (
    FileCreation,
    ProposedIssue,
    FileChangeRequest,
    PullRequest,
    RegexMatchError,
    SandboxResponse,
    SectionRewrite,
    Snippet,
    NoFilesException,
    Message,
    MaxTokensExceeded,
)

# from sandbox.modal_sandbox import SandboxError  # pylint: disable=E0401
from sweepai.core.prompts import (
    files_to_change_prompt,
    subissues_prompt,
    pull_request_prompt,
    create_file_prompt,
    modify_file_prompt_3,
    modify_file_system_message,
    snippet_replacement,
    chunking_prompt,
    RECREATE_LINE_LENGTH,
    modify_recreate_file_system_message,
    modify_recreate_file_prompt_3,
    rewrite_file_prompt,
    rewrite_file_system_prompt,
    snippet_replacement_system_message,
    fetch_snippets_system_prompt,
    fetch_snippets_prompt,
    update_snippets_system_prompt,
    update_snippets_prompt,
    python_files_to_change_prompt,
)
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DB_MODAL_INST_NAME, SANDBOX_URL, SECONDARY_MODEL
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.diff import (
    format_contents,
    generate_diff,
    generate_new_file_from_patch,
    is_markdown,
    get_matches,
    sliding_window_replacement,
)

from sweepai.utils.graph import Graph
from sweepai.utils.prompt_constructor import PythonHumanMessagePrompt
from sweepai.utils.search_and_replace import Match, find_best_match
from sweepai.utils.utils import chunk_code

USING_DIFF = True

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"


def strip_backticks(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s[s.find("\n") :]
    if s.endswith("```"):
        s = s[: s.rfind("\n")]
    return s.strip("\n")


def match_indent(generated: str, original: str) -> str:
    indent_type = "\t" if "\t" in original[:5] else " "
    generated_indents = len(generated) - len(generated.lstrip())
    target_indents = len(original) - len(original.lstrip())
    diff_indents = target_indents - generated_indents
    if diff_indents > 0:
        generated = indent_type * diff_indents + generated.replace(
            "\n", "\n" + indent_type * diff_indents
        )
    return generated


class CodeGenBot(ChatGPT):
    def summarize_snippets(self):
        # Custom system message for snippet replacement
        old_msg = self.messages[0].content
        self.messages[0].content = snippet_replacement_system_message

        snippet_summarization = self.chat(
            snippet_replacement,
            message_key="snippet_summarization",
        )  # maybe add relevant info

        self.messages[0].content = old_msg

        contextual_thought_match = re.search(
            "<contextual_thoughts>(?P<thoughts>.*)</contextual_thoughts>",
            snippet_summarization,
            re.DOTALL,
        )
        contextual_thought: str = (
            contextual_thought_match.group("thoughts").strip()
            if contextual_thought_match
            else ""
        )
        relevant_snippets_match = re.search(
            "<relevant_snippets>(?P<snippets>.*)</relevant_snippets>",
            snippet_summarization,
            re.DOTALL,
        )
        relevant_snippets: str = (
            relevant_snippets_match.group("snippets").strip()
            if relevant_snippets_match
            else ""
        )

        try:
            snippets: Snippet = []
            for raw_snippet in relevant_snippets.split("\n"):
                if ":" not in raw_snippet:
                    logger.warning(
                        f"Error in summarize_snippets: {raw_snippet}. Likely failed to"
                        " parse"
                    )
                file_path, lines = raw_snippet.split(":", 1)
                if "-" not in lines:
                    logger.warning(
                        f"Error in summarize_snippets: {raw_snippet}. Likely failed to"
                        " parse"
                    )
                start, end = lines.split("-", 1)
                start = int(start)
                end = int(end) - 1
                end = min(end, start + 200)

                snippet = Snippet(file_path=file_path, start=start, end=end, content="")
                snippets.append(snippet)

            self.populate_snippets(snippets)
            snippets = [snippet.expand() for snippet in snippets]
            snippets_text = "\n".join([snippet.xml for snippet in snippets])
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.warning(f"Error in summarize_snippets: {e}. Likely failed to parse")
            snippets_text = self.get_message_content_from_message_key(
                "relevant_snippets"
            )

        # Remove line numbers (1:line) from snippets
        snippets_text = re.sub(r"^\d+?:", "", snippets_text, flags=re.MULTILINE)

        msg_content = (
            "Contextual thoughts: \n"
            + contextual_thought
            + "\n\nRelevant snippets:\n\n"
            + snippets_text
            + "\n\n"
        )

        self.delete_messages_from_chat("relevant_snippets")
        self.delete_messages_from_chat("relevant_directories")
        self.delete_messages_from_chat("relevant_tree")
        self.delete_messages_from_chat("files_to_change", delete_assistant=False)
        self.delete_messages_from_chat("snippet_summarization")

        msg = Message(content=msg_content, role="assistant", key=BOT_ANALYSIS_SUMMARY)
        self.messages.insert(-2, msg)

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
        file_change_requests: list[FileChangeRequest] = []
        # Todo: put retries into a constants file
        # also, this retries multiple times as the calls for this function are in a for loop
        try:
            is_python_issue = (
                sum(
                    [
                        not file_path.endswith(".py")
                        for file_path in self.human_message.get_file_paths()
                    ]
                )
                < 2
            )
            logger.info(f"IS PYTHON ISSUE: {is_python_issue}")
            python_issue_worked = True
            if is_python_issue:
                graph = Graph.from_folder(folder_path=self.cloned_repo.cache_dir)
                graph_parent_bot = GraphParentBot(chat_logger=self.chat_logger)
                if pr_diffs is not None:
                    self.delete_messages_from_chat("pr_diffs")
                    graph_parent_bot.messages.insert(
                        1, Message(role="user", content=pr_diffs, key="pr_diffs")
                    )

                issue_metadata = self.human_message.get_issue_metadata()
                relevant_snippets = self.human_message.render_snippets()
                symbols_to_files = graph.paths_to_first_degree_entities(
                    self.human_message.get_file_paths()
                )
                if len(symbols_to_files) <= 1:
                    python_issue_worked = False

                if python_issue_worked:
                    (
                        relevant_files_to_symbols,
                        relevant_symbols_string,
                    ) = graph_parent_bot.relevant_files_to_symbols(
                        issue_metadata, relevant_snippets, symbols_to_files
                    )

                    file_paths_to_contents = {
                        file_path: self.cloned_repo.get_file_contents(file_path)
                        for file_path in relevant_files_to_symbols.keys()
                    }

                    # Create plan for relevant snippets first
                    human_message_snippet_paths = set(
                        s.file_path for s in self.human_message.snippets
                    )
                    non_human_message_snippet_paths = set()
                    for file_path in relevant_files_to_symbols.keys():
                        non_human_message_snippet_paths.add(
                            file_path
                        )  # TODO (luke) use trimmed context of initial files in this step instead of self.human_message.render_snippet_array(other_snippets)
                    plans: list[GraphContextAndPlan] = []
                    for file_path in (
                        human_message_snippet_paths | non_human_message_snippet_paths
                    ):
                        other_snippets = [
                            snippet
                            for snippet in self.human_message.snippets
                            if snippet.file_path != file_path
                            and file_path
                            in human_message_snippet_paths  # <- trim these once the human messages are parsed
                        ]
                        if file_path in human_message_snippet_paths:
                            snippet = next(
                                snippet
                                for snippet in self.human_message.snippets
                                if snippet.file_path == file_path
                            )
                        else:
                            snippet = Snippet(
                                file_path=file_path,
                                start=0,
                                end=0,
                                content=file_paths_to_contents[file_path],
                            )
                        relevant_symbol_list = []
                        for v in relevant_files_to_symbols.values():
                            relevant_symbol_list.extend(v)
                        plan_bot = GraphChildBot(chat_logger=self.chat_logger)
                        plan = plan_bot.code_plan_extraction(
                            code=snippet.content,
                            file_path=file_path,
                            entities=relevant_symbol_list,
                            issue_metadata=issue_metadata,
                            previous_snippets=self.human_message.render_snippet_array(
                                other_snippets
                            ),
                            all_symbols_and_files=relevant_symbols_string,
                        )
                        if plan.changes_for_new_file and plan.relevant_new_snippet:
                            plans.append(plan)

                    file_path_set = set()
                    deduped_plans = []
                    for plan in plans:
                        if plan.file_path not in file_path_set:
                            file_path_set.add(plan.file_path)
                            deduped_plans.append(plan)
                        else:
                            logger.info(f"Duplicate plan for {plan.file_path}")
                    plans = deduped_plans

                    # topologically sort the plans so that we can apply them in order
                    file_paths = [plan.file_path for plan in plans]
                    sorted_files = graph.topological_sort(file_paths)
                    sorted_plans = []
                    for file_path in sorted_files:
                        sorted_plans.append(
                            next(
                                plan for plan in plans if plan.file_path == file_path
                            )  # TODO: use a dict instead
                        )
                    plans = sorted_plans

                    relevant_snippets = self.human_message.snippets
                    for plan in plans:
                        self.populate_snippets(plan.relevant_new_snippet)
                        relevant_snippets.extend(plan.relevant_new_snippet)

                    plan_suggestions = []

                    for plan in plans:
                        plan_suggestions.append(
                            f"<plan_suggestion file={plan.file_path}>\n{plan.changes_for_new_file}\n</plan_suggestion>"
                        )

                    python_human_message = PythonHumanMessagePrompt(
                        repo_name=self.human_message.repo_name,
                        issue_url=self.human_message.issue_url,
                        username=self.human_message.username,
                        title=self.human_message.title,
                        summary=self.human_message.summary,
                        snippets=[],
                        tree=self.human_message.tree,
                        repo_description=self.human_message.repo_description,
                        plan_suggestions=plan_suggestions,
                    )
                    prompt_message_dicts = python_human_message.construct_prompt()
                    new_messages = [self.messages[0]]
                    for message_dict in prompt_message_dicts:
                        new_messages.append(Message(**message_dict))
                    self.messages = new_messages
                    file_change_requests = []
                    for plan in plans:
                        for snippet in plan.relevant_new_snippet:
                            file_change_requests.append(
                                FileChangeRequest(
                                    filename=snippet.file_path,
                                    instructions=plan.changes_for_new_file,
                                    change_type="modify",
                                    start_line=snippet.start,
                                    end_line=snippet.end,
                                )
                            )
                    return file_change_requests, " ".join(plan_suggestions)
            if not is_python_issue or not python_issue_worked:
                # Todo(wwzeng1): Integrate the plans list into the files_to_change_prompt optionally.
                if pr_diffs is not None:
                    self.delete_messages_from_chat("pr_diffs")
                    self.messages.insert(
                        1, Message(role="user", content=pr_diffs, key="pr_diffs")
                    )

                files_to_change_response = self.chat(
                    files_to_change_prompt, message_key="files_to_change"
                )  # Dedup files to change here
            file_change_requests = []
            for re_match in re.finditer(
                FileChangeRequest._regex, files_to_change_response, re.DOTALL
            ):
                file_change_requests.append(
                    FileChangeRequest.from_string(re_match.group(0))
                )
                
            if file_change_requests:
                return file_change_requests, files_to_change_response
        except RegexMatchError as e:
            logger.print(e)
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
                        pull_request_prompt, message_key="pull_request"
                    )
                else:
                    pr_text_response = self.chat(
                        pull_request_prompt,
                        message_key="pull_request",
                        model=SECONDARY_MODEL,
                    )

                # Add triple quotes if not present
                if not pr_text_response.strip().endswith('"""'):
                    pr_text_response += '"""'

                self.delete_messages_from_chat("pull_request")
            except SystemExit:
                raise SystemExit
            except Exception as e:
                e_str = str(e)
                if "too long" in e_str:
                    too_long = True
                logger.warning(f"Exception {e_str}. Failed to parse! Retrying...")
                self.delete_messages_from_chat("pull_request")
                continue
            pull_request = PullRequest.from_string(pr_text_response)

            # Remove duplicate slashes from branch name (max 1)
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

    def create_branch(self, branch: str, retry=True) -> str:
        # Generate PR if nothing is supplied maybe
        branch = self.clean_branch_name(branch)
        base_branch = self.repo.get_branch(SweepConfig.get_branch(self.repo))
        try:
            try:
                test = self.repo.get_branch("sweep")
                assert test is not None
                # If it does exist, fix
                branch = branch.replace(
                    "/", "_"
                )  # Replace sweep/ with sweep_ (temp fix)
            except SystemExit:
                raise SystemExit
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
                for i in range(1, 31):
                    try:
                        logger.warning(f"Retrying {branch}_{i}...")
                        self.repo.create_git_ref(
                            f"refs/heads/{branch}_{i}", base_branch.commit.sha
                        )
                        return f"{branch}_{i}"
                    except GithubException:
                        pass
            else:
                new_branch = self.repo.get_branch(branch)
                if new_branch:
                    return new_branch.name
            raise e

    def populate_snippets(self, snippets: list[Snippet]):
        for snippet in snippets:
            try:
                snippet.content = self.repo.get_contents(
                    snippet.file_path, SweepConfig.get_branch(self.repo)
                ).decoded_content.decode("utf-8")
                snippet.start = max(1, snippet.start)
                snippet.end = min(len(snippet.content.split("\n")), snippet.end)
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(snippet)

    @staticmethod
    def is_blocked(file_path: str, blocked_dirs: list[str]):
        for blocked_dir in blocked_dirs:
            if file_path.startswith(blocked_dir) and len(blocked_dir) > 0:
                return {"success": True, "path": blocked_dir}
        return {"success": False}

    def validate_file_change_requests(
        self, file_change_requests: list[FileChangeRequest], branch: str = ""
    ):
        blocked_dirs = get_blocked_dirs(self.repo)
        for file_change_request in file_change_requests:
            try:
                exists = False
                try:
                    exists = self.repo.get_contents(
                        file_change_request.filename,
                        branch or SweepConfig.get_branch(self.repo),
                    )
                except UnknownObjectException:
                    exists = False
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.error(f"FileChange Validation Error: {e}")

                if exists and file_change_request.change_type == "create":
                    file_change_request.change_type = "modify"
                elif not exists and file_change_request.change_type == "modify":
                    file_change_request.change_type = "create"

                block_status = self.is_blocked(
                    file_change_request.filename, blocked_dirs
                )
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
        file_change_requests = [
            file_change_request
            for file_change_request in file_change_requests
            if file_change_request.instructions.strip()
        ]
        return file_change_requests


class SweepBot(CodeGenBot, GithubBot):
    comment_pr_diff_str: str | None = None
    comment_pr_files_modified: Dict[str, str] | None = None

    @staticmethod
    def run_sandbox(
        repo_url: str,
        file_path: str,
        content: str | None,
        token: str,
        only_lint: bool = False,
    ) -> Dict:
        if not SANDBOX_URL:
            return {"success": False}

        response = requests.post(
            SANDBOX_URL,
            json={
                "token": token,
                "repo_url": repo_url,
                "file_path": file_path,
                "content": content,
                "only_lint": only_lint,
            },
            timeout=(5, 600),
        )
        response.raise_for_status()
        output = response.json()
        return output

    def check_completion(self, file_name: str, new_content: str) -> bool:
        can_check = False
        for ext in [".js", ".ts", ".jsx", ".tsx", ".py"]:
            if file_name.endswith(ext):
                can_check = True
                break
        if not can_check:
            return True

        # GPT-4 generated conditions
        # Checking for unimplemented Python code with NotImplementedError
        if "raise NotImplementedError" in new_content:
            return False

        # Checking for TODO or FIXME comments
        if "TODO" in new_content or "FIXME" in new_content:
            return False

        # Checking for Python functions with only a 'pass' statement
        if "def " in new_content and ":\n    pass\n" in new_content:
            return False

        # Checking for TypeScript/JavaScript functions that are empty
        if "function" in new_content and "){}" in new_content:
            return False

        # Checking for TypeScript/JavaScript arrow functions that are empty
        if ") => {}" in new_content:
            return False

        # Checking for abstract methods in TypeScript
        if "abstract" in new_content and "): void;" in new_content:
            return False

        # Checking for TypeScript/JavaScript methods that only contain a comment
        if (
            "function" in new_content
            and "){\n    // " in new_content
            and " \n}" in new_content
        ):
            return False

        return True

    def check_sandbox(
        self,
        file_path: str,
        content: str,
    ):
        # Format file
        sandbox_execution: SandboxResponse | None = None
        if SANDBOX_URL:
            try:
                logger.print("Running Sandbox...")
                logger.print(content)
                logger.print(self.sweep_context)
                output = SweepBot.run_sandbox(
                    token=self.sweep_context.token,
                    repo_url=self.repo.html_url,
                    file_path=file_path,
                    content=content,
                )
                logger.print(output)
                sandbox_execution = SandboxResponse(**output)
                if output["success"]:
                    content = output["updated_content"]
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(f"Sandbox Error: {e}")
                logger.error(traceback.format_exc())
        return content, sandbox_execution

    def create_file(
        self,
        file_change_request: FileChangeRequest,
        changed_files: list[tuple[str, str]] = [],
    ):
        file_change: FileCreation | None = None
        key = f"file_change_created_{file_change_request.filename}"
        if changed_files:
            changed_files_summary = "Changed files in this PR:\n\n" + "\n".join(
                [
                    f'<changed_file file_path="{file_path}">\n{file_contents}\n</changed_file>'
                    for file_path, file_contents in changed_files
                ]
            )
            self.messages.append(
                Message(
                    content=changed_files_summary,
                    role="assistant",
                    key="changed_files_summary",
                )
            )
        create_file_response = self.chat(
            create_file_prompt.format(
                filename=file_change_request.filename,
                instructions=file_change_request.instructions,
            ),
            message_key=key,
        )
        if changed_files:
            self.delete_messages_from_chat(key_to_delete="changed_files_summary")
        # Add file to list of changed_files
        self.file_change_paths.append(file_change_request.filename)
        # self.delete_file_from_system_message(file_path=file_change_request.filename)
        try:
            file_change = FileCreation.from_string(create_file_response)
            commit_message_match = re.search(
                'Commit message: "(?P<commit_message>.*)"', create_file_response
            )
            if commit_message_match:
                file_change.commit_message = commit_message_match.group(
                    "commit_message"
                )
            else:
                file_change.commit_message = f"Create {file_change_request.filename}"
            assert file_change is not None
            file_change.commit_message = file_change.commit_message[
                : min(len(file_change.commit_message), 50)
            ]

            self.delete_messages_from_chat(key_to_delete=key)

            try:
                implemented = self.check_completion(  # use async
                    file_change_request.filename, file_change.code
                )
                if not implemented:
                    discord_log_error(
                        f"{self.sweep_context.issue_url}\nUnimplemented Create Section: {'gpt3.5' if self.sweep_context.use_faster_model else 'gpt4'}: \n",
                        priority=2 if self.sweep_context.use_faster_model else 0,
                    )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(f"Error: {e}")

            file_change.code, sandbox_execution = self.check_sandbox(
                file_change_request.filename, file_change.code
            )

            return file_change, sandbox_execution
        except SystemExit:
            raise SystemExit
        except Exception as e:
            # Todo: should we undo appending to file_change_paths?
            logger.info(traceback.format_exc())
            logger.warning(e)
            logger.warning(f"Failed to parse. Retrying for the 1st time...")
            self.delete_messages_from_chat(key)
        raise Exception("Failed to parse response after 5 attempts.")

    def modify_file(
        self,
        file_change_request: FileChangeRequest,
        contents: str = "",
        contents_line_numbers: str = "",
        branch=None,
        chunking: bool = False,
        chunk_offset: int = 0,
        sandbox=None,
        changed_files: list[tuple[str, str]] = [],
    ):
        key = f"file_change_modified_{file_change_request.filename}"
        file_markdown = is_markdown(file_change_request.filename)
        # TODO(sweep): edge case at empty file
        new_file = ""
        try:
            file_path_to_contents = OrderedDict()
            for file_path, diffs in changed_files:
                if not diffs.strip():
                    continue
                if file_path in file_path_to_contents:
                    file_path_to_contents[file_path] += diffs
                else:
                    file_path_to_contents[file_path] = diffs
            changed_files_summary = "We have previously changed these files:\n" + "\n".join(
                [
                    f'<changed_file file_path="{file_path}">\n{diffs}\n</changed_file>'
                    for file_path, diffs in file_path_to_contents.items()
                ]
            )
            additional_messages = (
                [
                    Message(
                        content=changed_files_summary,
                        role="user",
                    )
                ]
                if changed_files
                else []
            )
            if self.comment_pr_diff_str:
                additional_messages += [
                    Message(
                        role="user", content=self.comment_pr_diff_str, key="pr_diffs"
                    )
                ]
            additional_messages += (
                [
                    Message(
                        content="This is one of the sections of code out of a larger body of code and the changes may not be in this file. If you do not wish to make changes to this file, please type `skip`.",
                        role="assistant",
                    )
                ]
                if chunking
                else []
            )
            modify_file_bot = ModifyBot(
                additional_messages,
                parent_bot=self,
                chat_logger=self.chat_logger,
            )
            try:
                new_file = modify_file_bot.try_update_file(
                    file_path=file_change_request.filename,
                    file_contents=contents,
                    file_change_request=file_change_request,
                    chunking=chunking,
                )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                if chunking:
                    return contents, "", None, changed_files
                raise e
        except SystemExit:
            raise SystemExit
        except Exception as e:  # Check for max tokens error
            if "max tokens" in str(e).lower():
                logger.error(f"Max tokens exceeded for {file_change_request.filename}")
                raise MaxTokensExceeded(file_change_request.filename)
            else:
                logger.error(f"Error: {e}")
                logger.error(traceback.format_exc())
                self.delete_messages_from_chat(key)
                raise e
        try:
            new_file = format_contents(new_file, file_markdown)
            commit_message_match = None
            if commit_message_match:
                commit_message = commit_message_match.group("commit_message")
            else:
                commit_message = f"feat: Updated {file_change_request.filename}"
            commit_message = commit_message[: min(len(commit_message), 50)]

            sandbox_execution = None
            if not chunking:
                new_file, sandbox_execution = self.check_sandbox(
                    file_change_request.filename, new_file
                )
            changed_files.append(
                (
                    file_change_request.filename,
                    generate_diff(contents, new_file),
                )
            )
            return new_file, commit_message, sandbox_execution, changed_files
        except SystemExit:
            raise SystemExit
        except Exception as e:
            tb = traceback.format_exc()
            logger.warning(f"Failed to parse." f" {e}\n{tb}")
            self.delete_messages_from_chat(key)
        raise Exception(f"Failed to parse response after 1 attempt.")

    def rewrite_section(
        self,
        file_change_request: FileChangeRequest,
        contents: str,
        section: str,
    ) -> FileCreation:
        section_rewrite: SectionRewrite | None = None
        key = f"file_change_created_{file_change_request.filename}"
        old_system_message = self.messages[0].content
        self.messages[0].content = rewrite_file_system_prompt
        rewrite_section_response = self.chat(
            rewrite_file_prompt.format(
                filename=file_change_request.filename,
                code=contents,
                instructions=file_change_request.instructions,
                section=section,
            ),
            message_key=key,
        )
        self.messages[0].content = old_system_message
        self.file_change_paths.append(file_change_request.filename)
        try:
            section_rewrite = SectionRewrite.from_string(rewrite_section_response)
            self.delete_messages_from_chat(key_to_delete=key)

            try:
                implemented = self.check_completion(  # use async
                    file_change_request.filename, section_rewrite.section
                )
                if not implemented:
                    discord_log_error(
                        f"{self.sweep_context.issue_url}\nUnimplemented Create Section: {'gpt3.5' if self.sweep_context.use_faster_model else 'gpt4'}: \n",
                        priority=2 if self.sweep_context.use_faster_model else 0,
                    )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(f"Error: {e}")

            return section_rewrite
        except SystemExit:
            raise SystemExit
        except Exception as e:
            # Todo: should we undo appending to file_change_paths?
            logger.info(traceback.format_exc())
            logger.warning(e)
            logger.warning(f"Failed to parse. Retrying for the 1st time...")
            self.delete_messages_from_chat(key)
        raise Exception("Failed to parse response after 5 attempts.")

    def rewrite_file(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
    ) -> FileCreation:
        chunks = []
        original_file = self.repo.get_contents(file_change_request.filename, ref=branch)
        original_contents = original_file.decoded_content.decode("utf-8")
        contents = original_contents
        for snippet in chunk_code(
            contents, file_change_request.filename, MAX_CHARS=2300, coalesce=200
        ):
            chunks.append(snippet.get_snippet(add_ellipsis=False, add_lines=False))
        for i, chunk in enumerate(chunks):
            section_rewrite = self.rewrite_section(file_change_request, contents, chunk)
            chunks[i] = section_rewrite.section
            contents = "\n".join(chunks)

        commit_message = (
            f"Rewrote {file_change_request.filename} to do "
            + file_change_request.instructions[
                : min(len(file_change_request.instructions), 30)
            ]
        )
        final_contents, sandbox_execution = self.check_sandbox(
            file_change_request.filename, contents
        )
        self.repo.update_file(
            file_change_request.filename,
            commit_message,
            final_contents,
            sha=original_file.sha,
            branch=branch,
        )
        return final_contents != original_contents, sandbox_execution

    def change_files_in_github(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str,
        blocked_dirs: list[str] = [],
        sandbox=None,
    ):
        # should check if branch exists, if not, create it
        logger.debug(file_change_requests)
        num_fcr = len(file_change_requests)
        completed = 0

        for _, changed_file in self.change_files_in_github_iterator(
            file_change_requests, branch, blocked_dirs, sandbox=sandbox
        ):
            if changed_file:
                completed += 1
        return completed, num_fcr

    def change_files_in_github_iterator(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str,
        blocked_dirs: list[str],
        sandbox=None,
    ) -> Generator[tuple[FileChangeRequest, bool], None, None]:
        # should check if branch exists, if not, create it
        logger.debug(file_change_requests)
        # num_fcr = len(file_change_requests)
        completed = 0
        sandbox_execution = None

        # added_modify_hallucination = False

        LINE_CUTOFF = 600
        changed_files: list[tuple[str, str]] = []

        for file_change_request in file_change_requests:
            logger.print(file_change_request.change_type, file_change_request.filename)
            changed_file = False

            # popping files too long
            # total_lines = 0
            # new_changed_files = []
            # for file_name, changed_file in changed_files:
            #     if total_lines + len(changed_file.splitlines()) > LINE_CUTOFF:
            #         break
            #     new_changed_files.append((file_name, changed_file))
            #     total_lines += len(changed_file.splitlines())
            # changed_files = new_changed_files

            try:
                commit = None
                # Todo(Sweep): add commit for each type of change type
                if self.is_blocked(file_change_request.filename, blocked_dirs)[
                    "success"
                ]:
                    logger.info(
                        f"Skipping {file_change_request.filename} because it is"
                        " blocked."
                    )
                    continue

                logger.print(
                    f"Processing {file_change_request.filename} for change type"
                    f" {file_change_request.change_type}..."
                )
                match file_change_request.change_type:
                    case "create":
                        (
                            changed_file,
                            sandbox_execution,
                            commit,
                        ) = self.handle_create_file(
                            file_change_request,
                            branch,
                            sandbox=sandbox,
                            changed_files=changed_files,
                        )
                        changed_files.append(
                            (
                                file_change_request.filename,
                                file_change_request.new_content,
                            )
                        )
                    case "modify" | "rewrite":
                        # Remove snippets from this file if they exist
                        snippet_msgs = [
                            m for m in self.messages if m.key == BOT_ANALYSIS_SUMMARY
                        ]
                        if len(snippet_msgs) > 0:  # Should always be true
                            snippet_msg = snippet_msgs[0]
                            # Use regex to remove this snippet from the message
                            file = re.escape(file_change_request.filename)
                            regex = rf'<snippet source="{file}:\d*-?\d*.*?<\/snippet>'
                            snippet_msg.content = re.sub(
                                regex,
                                "",
                                snippet_msg.content,
                                flags=re.DOTALL,
                            )
                        file_change_request.new_content
                        (
                            changed_file,
                            sandbox_execution,
                            commit,
                            changed_files,
                        ) = self.handle_modify_file(
                            file_change_request,
                            branch,
                            sandbox=sandbox,
                            changed_files=changed_files,
                        )
                    case "delete":
                        contents = self.repo.get_contents(
                            file_change_request.filename, ref=branch
                        )
                        self.repo.delete_file(
                            file_change_request.filename,
                            f"Deleted {file_change_request.filename}",
                            sha=contents.sha,
                            branch=branch,
                        )
                        changed_file = True
                    case "rename":
                        contents = self.repo.get_contents(
                            file_change_request.filename, ref=branch
                        )
                        self.repo.create_file(
                            file_change_request.instructions,
                            (
                                f"Renamed {file_change_request.filename} to"
                                f" {file_change_request.instructions}"
                            ),
                            contents.decoded_content,
                            branch=branch,
                        )
                        self.repo.delete_file(
                            file_change_request.filename,
                            f"Deleted {file_change_request.filename}",
                            sha=contents.sha,
                            branch=branch,
                        )
                        changed_file = True
                    case _:
                        raise Exception(
                            f"Unknown change type {file_change_request.change_type}"
                        )
                logger.print(f"Done processing {file_change_request.filename}.")
                yield file_change_request, changed_file, sandbox_execution, commit
            except MaxTokensExceeded as e:
                raise e
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(f"Error in change_files_in_github {e}")

            if changed_file:
                completed += 1

    def handle_create_file(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        sandbox=None,
        changed_files: list[tuple[str, str]] = [],
    ) -> tuple[bool, None, Commit]:
        try:
            file_change, sandbox_execution = self.create_file(
                file_change_request, changed_files=changed_files
            )
            file_markdown = is_markdown(file_change_request.filename)
            file_change.code = format_contents(file_change.code, file_markdown)
            logger.debug(
                f"{file_change_request.filename},"
                f" {f'Create {file_change_request.filename}'}, {file_change.code},"
                f" {branch}"
            )

            result = self.repo.create_file(
                file_change_request.filename,
                file_change.commit_message,
                file_change.code,
                branch=branch,
            )

            file_change_request.new_content = file_change.code

            return True, sandbox_execution, result["commit"]
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.info(f"Error in handle_create_file: {e}")
            return False, None, None

    def handle_modify_file(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        commit_message: str = None,
        sandbox=None,
        changed_files: list[tuple[str, str]] = [],
    ) -> tuple[str, Any, Commit, list]:
        CHUNK_SIZE = 800  # Number of lines to process at a time
        sandbox_error = None
        try:
            file = self.get_file(file_change_request.filename, branch=branch)
            file_contents = file.decoded_content.decode("utf-8")
            lines = file_contents.split("\n")

            new_file_contents = ""
            all_lines_numbered = [f"{i + 1}:{line}" for i, line in enumerate(lines)]
            # Todo(lukejagg): Use when only using chunking
            chunk_sizes = [
                # 800,
                600,
                400,
                # 300,
            ]  # Define the chunk sizes for the backoff mechanism
            if file_change_request.start_line is not None and file_change_request.end_line is not None:
                chunk_sizes = [10000] # dont chunk if we know the start and end lines already
            for CHUNK_SIZE in chunk_sizes:
                try:
                    chunking = (
                        len(lines) > CHUNK_SIZE
                    )  # Only chunk if the file is large enough
                    file_name = file_change_request.filename
                    if not chunking:
                        (
                            new_file_contents,
                            suggested_commit_message,
                            sandbox_error,
                            changed_files,
                        ) = self.modify_file(
                            file_change_request,
                            contents="\n".join(lines),
                            branch=branch,
                            contents_line_numbers=file_contents
                            if USING_DIFF
                            else "\n".join(all_lines_numbered),
                            chunking=chunking,
                            chunk_offset=0,
                            sandbox=sandbox,
                            changed_files=changed_files,
                        )
                        commit_message = suggested_commit_message
                        # commit_message = commit_message or suggested_commit_message
                    else:
                        for i in range(0, len(lines), CHUNK_SIZE):
                            chunk_contents = "\n".join(lines[i : i + CHUNK_SIZE])
                            contents_line_numbers = "\n".join(
                                all_lines_numbered[i : i + CHUNK_SIZE]
                            )
                            # if not EditBot().should_edit(
                            #     issue=file_change_request.instructions,
                            #     snippet=chunk_contents,
                            # ):
                            #     new_chunk = chunk_contents
                            # else:
                            (
                                new_chunk,
                                suggested_commit_message,
                                sandbox_error,
                                changed_files,
                            ) = self.modify_file(
                                file_change_request,
                                contents=chunk_contents,
                                branch=branch,
                                contents_line_numbers=chunk_contents
                                if USING_DIFF
                                else "\n".join(contents_line_numbers),
                                chunking=chunking,
                                chunk_offset=i,
                                sandbox=sandbox,
                                changed_files=changed_files,
                            )
                            # commit_message = commit_message or suggested_commit_message
                            commit_message = suggested_commit_message
                            if i + CHUNK_SIZE < len(lines):
                                new_file_contents += new_chunk + "\n"
                            else:
                                new_file_contents += new_chunk
                    break  # If the chunking was successful, break the loop
                except Exception as e:
                    logger.print(e)
                    raise e

                    continue  # If the chunking was not successful, continue to the next chunk size
            # If the original file content is identical to the new file content, log a warning and return
            if file_contents == new_file_contents:
                logger.warning(
                    f"No changes made to {file_change_request.filename}. Skipping file"
                    " update."
                )
                return False, sandbox_error, "No changes made to file.", changed_files
            logger.debug(
                f"{file_name}, {commit_message}, {new_file_contents}, {branch}"
            )

            # Update the file with the new contents after all chunks have been processed
            try:
                result = self.repo.update_file(
                    file_name,
                    # commit_message.format(file_name=file_name),
                    commit_message,
                    new_file_contents,
                    file.sha,
                    branch=branch,
                )
                file_change_request.new_content = new_file_contents
                return True, sandbox_error, result["commit"], changed_files
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.info(f"Error in updating file, repulling and trying again {e}")
                file = self.get_file(file_change_request.filename, branch=branch)
                result = self.repo.update_file(
                    file_name,
                    # commit_message.format(file_name=file_name),
                    commit_message,
                    new_file_contents,
                    file.sha,
                    branch=branch,
                )
                file_change_request.new_content = new_file_contents
                return True, sandbox_error, result["commit"], changed_files
        except MaxTokensExceeded as e:
            raise e
        except SystemExit:
            raise SystemExit
        except Exception as e:
            tb = traceback.format_exc()
            logger.info(f"Error in handle_modify_file: {tb}")
            return False, sandbox_error, None, changed_files


class ModifyBot:
    def __init__(
        self,
        additional_messages: list[Message] = [],
        chat_logger=None,
        parent_bot: SweepBot = None,
    ):
        self.fetch_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            fetch_snippets_system_prompt, chat_logger=chat_logger
        )
        self.fetch_snippets_bot.messages.extend(additional_messages)
        self.update_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            update_snippets_system_prompt, chat_logger=chat_logger
        )
        self.update_snippets_bot.messages.extend(additional_messages)
        self.parent_bot = parent_bot

    def try_update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        snippet_queries = self.get_snippets_to_modify(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            chunking=chunking,
        )
        
        new_file = self.update_file(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            snippet_queries=snippet_queries,
            chunking=chunking,
        )
        return new_file

    def get_snippets_to_modify(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        fetch_snippets_response = self.fetch_snippets_bot.chat(
            fetch_snippets_prompt.format(
                code=file_contents,
                file_path=file_path,
                request=file_change_request.instructions,
                chunking_prompt='\nThe request may not apply to this section of the code. If so, reply with "No changes needed"\n'
                if chunking
                else "",
            )
        )

        snippet_queries = []
        query_pattern = r'<snippet_to_modify>(?P<code>.*?)</snippet_to_modify>'
        for code in re.findall(
            query_pattern, fetch_snippets_response, re.DOTALL
        ):
            snippet_queries.append(strip_backticks(code))

        assert len(snippet_queries) > 0, "No snippets found in file"
        return snippet_queries

    def update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        snippet_queries: list[str],
        chunking: bool = False,
    ):
        best_matches = []
        for query in snippet_queries:
            _match = find_best_match(query, file_contents)
            if _match.score > 50:
                best_matches.append(_match)

        assert len(best_matches) > 0, "No matches found in file"

        # Todo: check multiple files for matches using PR changed files

        best_matches.sort(key=lambda x: x.start + x.end * 0.001)

        def fuse_matches(a: Match, b: Match) -> Match:
            return Match(
                start=min(a.start, b.start),
                end=max(a.end, b.end),
                score=min(a.score, b.score),
            )

        current_match = best_matches[0]
        deduped_matches = []

        # Fuse & dedup
        for _match in best_matches:
            if current_match.end > _match.start:
                current_match = fuse_matches(current_match, _match)
            else:
                deduped_matches.append(current_match)
                current_match = _match
        deduped_matches.append(current_match)

        # import pdb; pdb.set_trace()
        selected_snippets = []
        for _match in deduped_matches:
            current_contents = "\n".join(file_contents.split("\n")[_match.start : _match.end])
            selected_snippets.append(current_contents)

        print(deduped_matches)
        if file_change_request.start_line is not None and file_change_request.end_line is not None:
            split_file_contents = "\n".join(file_contents.split("\n")[file_change_request.start_line - 1: file_change_request.end_line])
            plan_extracted_contents = ""
            for idx, line in enumerate(split_file_contents.split("\n")):
                plan_extracted_contents += f"{idx + file_change_request.start_line}: {line}\n"
        else:
            plan_extracted_contents = file_contents
        update_snippets_response = self.update_snippets_bot.chat(
            update_snippets_prompt.format(
                code=plan_extracted_contents,
                file_path=file_path,
                snippets="\n\n".join(
                    [
                        f'<snippet>\n{snippet}\n</snippet>'
                        for i, snippet in enumerate(selected_snippets)
                    ]
                ),
                request=file_change_request.instructions,
            )
        )

        updated_snippets = []
        updated_pattern = (
            r"<updated_snippet>(?P<code>.*?)</updated_snippet>"
        )
        for code in re.findall(
            updated_pattern, update_snippets_response, re.DOTALL
        ):
            updated_snippets.append(strip_backticks(code))

        result = file_contents
        for search, replace in zip(
            selected_snippets, updated_snippets
        ):
            result, _, _ = sliding_window_replacement(
                result.splitlines(),
                search.splitlines(),
                match_indent(replace, search).splitlines(),
            )
            result = "\n".join(result)

        ending_newlines = len(file_contents) - len(file_contents.rstrip("\n"))
        result = result.rstrip("\n") + "\n" * ending_newlines

        return result


if __name__ == "__main__":
    response = """
```python
```"""
    stripped = strip_backticks(response)
    print(stripped)
