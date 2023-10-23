import copy
import hashlib
import re
import traceback
import uuid
from collections import OrderedDict
from typing import Dict, Generator

import requests
from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from pydantic import BaseModel

from sweepai.agents.complete_code import ExtractLeftoverComments
from sweepai.agents.graph_child import (
    GraphChildBot,
    GraphContextAndPlan,
    extract_python_span,
)
from sweepai.agents.graph_parent import GraphParentBot
from sweepai.agents.prune_modify_snippets import PruneModifySnippets
from sweepai.agents.validate_code import ChangeValidation, ChangeValidator
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DEBUG, MINIS3_URL, SANDBOX_URL, SECONDARY_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import (
    FileChangeRequest,
    FileCreation,
    MaxTokensExceeded,
    Message,
    NoFilesException,
    ProposedIssue,
    PullRequest,
    RegexMatchError,
    SandboxResponse,
    SectionRewrite,
    Snippet,
    UnneededEditError,
)

# from sandbox.modal_sandbox import SandboxError  # pylint: disable=E0401
from sweepai.core.prompts import (
    create_file_prompt,
    dont_use_chunking_message,
    fetch_snippets_prompt,
    fetch_snippets_system_prompt,
    files_to_change_prompt,
    pull_request_prompt,
    python_files_to_change_prompt,
    rewrite_file_prompt,
    rewrite_file_system_prompt,
    sandbox_files_to_change_prompt,
    snippet_replacement,
    snippet_replacement_system_message,
    subissues_prompt,
    use_chunking_message,
)
from sweepai.core.update_prompts import (
    update_snippets_prompt,
    update_snippets_prompt_test,
    update_snippets_system_prompt,
    update_snippets_system_prompt_python,
)
from sweepai.logn import logger
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.code_tree import CodeTree
from sweepai.utils.diff import (
    format_contents,
    generate_diff,
    is_markdown,
    sliding_window_replacement,
)
from sweepai.utils.function_call_utils import find_function_calls
from sweepai.utils.graph import Graph
from sweepai.utils.search_and_replace import Match, find_best_match, split_ellipses
from sweepai.utils.utils import chunk_code

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"
to_raw_string = lambda s: repr(s).lstrip("u")[1:-1]

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


def strip_backticks(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s[s.find("\n") :]
    if s.endswith("```"):
        s = s[: s.rfind("\n")]
    s = s.strip("\n")
    if s == '""':
        return ""
    return s


def remove_line_numbers(s: str) -> str:
    # Check if more than 50% of lines have line numbers
    # Remove line numbers with spaces after (e.g. "1: {code}")
    if len(re.findall(r"\d+?: ", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?: ", "", s, flags=re.MULTILINE)

    # Remove line numbers with no space after (e.g. "112:{code}")
    if len(re.findall(r"\d+?:", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?:", "", s, flags=re.MULTILINE)
    return s


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
        self, is_python_issue: bool, retries=1, pr_diffs: str | None = None
    ) -> tuple[list[FileChangeRequest], str]:
        file_change_requests: list[FileChangeRequest] = []
        # Todo: put retries into a constants file
        # also, this retries multiple times as the calls for this function are in a for loop
        try:
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

                    file_paths_to_contents = {}
                    for file_path in relevant_files_to_symbols.keys():
                        try:
                            file_paths_to_contents[
                                file_path
                            ] = self.cloned_repo.get_file_contents(file_path)
                        except FileNotFoundError:
                            logger.warning(
                                f"File {file_path} not found in repo. Skipping..."
                            )
                            continue

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
                            if file_path in file_paths_to_contents:
                                snippet = Snippet(
                                    file_path=file_path,
                                    start=0,
                                    end=0,
                                    content=file_paths_to_contents[file_path],
                                )
                            else:
                                continue
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
                        if plan.relevant_new_snippet:
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

                    relevant_snippet_text = ""
                    for plan in plans:
                        extracted_code = plan.relevant_new_snippet[0].content
                        if len(relevant_snippet_text) + len(extracted_code) < 60000:
                            relevant_snippet_text += f"<relevant_snippet file_path={plan.file_path}>\n{extracted_code}\n</relevant_snippet>\n"
                    relevant_snippet_text = relevant_snippet_text.strip("\n")
                    relevant_snippet_text = f"<relevant_snippets>\n{relevant_snippet_text}\n</relevant_snippets>"
                    self.update_message_content_from_message_key(
                        "relevant_snippets", relevant_snippet_text
                    )
                    files_to_change_response = self.chat(
                        python_files_to_change_prompt, message_key="files_to_change"
                    )  # Dedup files to change here
                    file_change_requests = []
                    for re_match in re.finditer(
                        FileChangeRequest._regex, files_to_change_response, re.DOTALL
                    ):
                        file_change_request = FileChangeRequest.from_string(
                            re_match.group(0)
                        )
                        file_change_requests.append(file_change_request)
                        if file_change_request.change_type in ("modify", "create"):
                            new_file_change_request = copy.deepcopy(file_change_request)
                            new_file_change_request.change_type = "check"
                            new_file_change_request.parent = file_change_request
                            new_file_change_request.id_ = str(uuid.uuid4())
                            file_change_requests.append(new_file_change_request)

                    if file_change_requests:
                        plan_str = "\n".join(
                            [fcr.instructions_display for fcr in file_change_requests]
                        )
                        return file_change_requests, plan_str
            if not is_python_issue or not python_issue_worked:
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
                file_change_request = FileChangeRequest.from_string(re_match.group(0))
                file_change_requests.append(file_change_request)
                if file_change_request.change_type in ("modify", "create"):
                    new_file_change_request = copy.deepcopy(file_change_request)
                    new_file_change_request.change_type = "check"
                    new_file_change_request.parent = file_change_request
                    new_file_change_request.id_ = str(uuid.uuid4())
                    file_change_requests.append(new_file_change_request)

            if file_change_requests:
                plan_str = "\n".join(
                    [fcr.instructions_display for fcr in file_change_requests]
                )
                return file_change_requests, plan_str
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
                    for prefix in [
                        self.repo.full_name,
                        self.repo.owner.login,
                        self.repo.name,
                    ]:
                        try:
                            new_filename = file_change_request.filename.replace(
                                prefix + "/", "", 1
                            )
                            exists = self.repo.get_contents(
                                new_filename,
                                branch or SweepConfig.get_branch(self.repo),
                            )
                            file_change_request.filename = new_filename
                            break
                        except UnknownObjectException:
                            pass
                    else:
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
                raise e
        file_change_requests = [
            file_change_request
            for file_change_request in file_change_requests
            if file_change_request.instructions.strip()
        ]
        return file_change_requests


ASSET_BRANCH_NAME = "sweep/assets"


class SweepBot(CodeGenBot, GithubBot):
    comment_pr_diff_str: str | None = None
    comment_pr_files_modified: Dict[str, str] | None = None

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

    def update_asset(
        self,
        file_path: str,
        content: str,
    ):
        hash_ = hashlib.sha256(content.encode("utf-8")).hexdigest()
        file_path = f"{hash_}_{file_path}"
        try:
            response = requests.post(
                MINIS3_URL, json={"filename": file_path, "content": content}
            )
            response.raise_for_status()
            return MINIS3_URL.rstrip("/") + response.json()["url"]
        except Exception as e:
            logger.error(e)
            self.init_asset_branch()
            try:
                fetched_content = self.repo.get_contents(file_path, ASSET_BRANCH_NAME)
                self.repo.update_file(
                    file_path,
                    "Update " + file_path,
                    content,
                    fetched_content.sha,
                    branch=ASSET_BRANCH_NAME,
                )
            except UnknownObjectException:
                self.repo.create_file(
                    file_path,
                    "Add " + file_path,
                    content,
                    branch=ASSET_BRANCH_NAME,
                )
            return f"https://raw.githubusercontent.com/{self.repo.full_name}/{ASSET_BRANCH_NAME}/{file_path}"

    @staticmethod
    # @file_cache(ignore_params=["token"])
    def run_sandbox(
        repo_url: str,
        file_path: str,
        content: str | None,
        token: str,
        changed_files: list[tuple[str, str]],
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
                "changed_files": {
                    file_path: new_contents
                    for file_path, (_old_contents, new_contents) in changed_files
                },
                "only_lint": only_lint,
                "do_fix": False,
            },
            timeout=(5, 500),
        )
        response.raise_for_status()
        output = response.json()
        return output

    def check_completion(self, file_name: str, new_content: str) -> bool:
        return True

    def check_sandbox(
        self,
        file_path: str,
        content: str,
        changed_files: list[tuple[str, str]],
    ):
        # Format file
        sandbox_execution: SandboxResponse | None = None
        if SANDBOX_URL:
            try:
                logger.info(f"Running sandbox for {file_path}...")
                output = SweepBot.run_sandbox(
                    token=self.sweep_context.token,
                    repo_url=self.repo.html_url,
                    file_path=file_path,
                    content=content,
                    changed_files=changed_files,
                )
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
        old_messages = self.messages
        if changed_files:
            file_path_to_contents = OrderedDict()
            for file_path, (old_contents, new_contents) in changed_files:
                if not new_contents.strip():
                    continue
                diffs = generate_diff(old_contents, new_contents)
                if file_path in file_path_to_contents:
                    file_path_to_contents[file_path] += diffs
                else:
                    file_path_to_contents[file_path] = diffs
            changed_files_summary = "Changed files in this PR:\n\n" + "\n".join(
                [
                    f'<changed_file file_path="{file_path}">\n{diffs}\n</changed_file>'
                    for file_path, diffs in file_path_to_contents.items()
                ]
            )
            self.messages.append(
                Message(
                    content=changed_files_summary,
                    role="user",
                    key="changed_files_summary",
                )
            )
        self.delete_messages_from_chat(key_to_delete="files_to_change")
        if file_change_request.relevant_files:
            relevant_files_contents = []
            for file_path in file_change_request.relevant_files:
                try:
                    relevant_files_contents.append(
                        self.get_contents(
                            file_path, branch=self.cloned_repo.branch
                        ).decoded_content.decode("utf-8")
                    )
                except Exception as e:
                    relevant_files_contents.append("File not found")
            if relevant_files_contents:
                relevant_files_summary = "Relevant files in this PR:\n\n" + "\n".join(
                    [
                        f'<relevant_file file_path="{file_path}">\n{file_contents}\n</relevant_file>'
                        for file_path, file_contents in zip(
                            file_change_request.relevant_files, relevant_files_contents
                        )
                    ]
                )
                self.messages.append(
                    Message(
                        content=relevant_files_summary,
                        role="user",
                        key="relevant_files_summary",
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
        file_change = FileCreation.from_string(create_file_response)
        extract_leftover_comments_bot = ExtractLeftoverComments(
            chat_logger=self.chat_logger
        )
        extract_leftover_comments_bot.messages = copy.deepcopy(
            self.messages[:-2]
        )  # deletes the request
        leftover_comments = (
            extract_leftover_comments_bot.extract_leftover_comments(
                file_change.code,
                file_change_request.filename,
                file_change_request.instructions,
            )
            if not DEBUG
            else []
        )
        if leftover_comments and not DEBUG:
            file_contents = file_change.code
            new_fcr = copy.deepcopy(file_change_request)
            joined_comments = "\n".join(leftover_comments)
            new_fcr.instructions = (
                f"Address all of the unfinished code changes here: \n{joined_comments}"
            )
            (
                file_contents,
                _,
                _,
                _,  # Don't use changed_files here
            ) = self.modify_file(
                new_fcr,
                contents=file_contents,
                changed_files=changed_files,
            )
            file_change.code = file_contents
        commit_message_match = re.search(
            'Commit message: "(?P<commit_message>.*)"', create_file_response
        )
        if commit_message_match:
            file_change.commit_message = commit_message_match.group("commit_message")
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

        # file_change.code, sandbox_execution = self.check_sandbox(
        #     file_change_request.filename, file_change.code, changed_files
        # )
        sandbox_execution = None

        self.messages = old_messages

        return file_change, sandbox_execution

    def modify_file(
        self,
        file_change_request: FileChangeRequest,
        contents: str = "",
        chunking: bool = False,
        branch: str = None,
        changed_files: list[tuple[str, str]] = [],
        temperature: float = 0.0,
    ):
        key = f"file_change_modified_{file_change_request.filename}"
        new_file = None
        sandbox_execution = None
        try:
            additional_messages = [
                Message(
                    role="user",
                    content=self.human_message.get_issue_metadata(),
                    key="issue_metadata",
                )
            ]
            if self.comment_pr_diff_str and self.comment_pr_diff_str.strip():
                additional_messages = [
                    Message(
                        role="user",
                        content="These changes have already been made:\n"
                        + self.comment_pr_diff_str,
                        key="pr_diffs",
                    )
                ]
            file_path_to_contents = OrderedDict()
            for file_path, (old_contents, new_contents) in changed_files:
                diffs = generate_diff(old_contents, new_contents)
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
            if changed_files:
                additional_messages += [
                    Message(
                        content=changed_files_summary,
                        role="user",
                        key="changed_files_summary",
                    )
                ]
            if file_change_request.relevant_files:
                relevant_files_contents = []
                for file_path in file_change_request.relevant_files:
                    try:
                        relevant_files_contents.append(
                            self.get_contents(file_path).decoded_content.decode("utf-8")
                        )
                    except Exception as e:
                        relevant_files_contents.append("File not found")
                if relevant_files_contents:
                    relevant_files_summary = "Relevant files in this PR:\n\n" + "\n".join(
                        [
                            f'<relevant_file file_path="{file_path}">\n{file_contents}\n</relevant_file>'
                            for file_path, file_contents in zip(
                                file_change_request.relevant_files,
                                relevant_files_contents,
                            )
                        ]
                    )
                    additional_messages.append(
                        Message(
                            content=relevant_files_summary,
                            role="user",
                            key="relevant_files_summary",
                        )
                    )
            current_file_diff = ""
            if changed_files:
                for file_path, (old_contents, new_contents) in changed_files:
                    if file_path == file_change_request.filename:
                        current_file_diff += (
                            generate_diff(old_contents, new_contents) + "\n"
                        )
            modify_file_bot = ModifyBot(
                additional_messages,
                parent_bot=self,
                chat_logger=self.chat_logger,
                old_file_contents=contents,
                current_file_diff=current_file_diff,
                is_pr=bool(self.comment_pr_diff_str),
                temperature=temperature,
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
            except UnneededEditError as e:
                if chunking:
                    return contents, f"feat: Updated {file_change_request.filename}", None, changed_files
                raise e
            except Exception as e:
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
            commit_message = f"feat: Updated {file_change_request.filename}"
            commit_message = commit_message[: min(len(commit_message), 50)]
            changed_files.append(
                (
                    file_change_request.filename,
                    (
                        contents,
                        new_file,
                    ),
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

    def get_files_to_change_from_sandbox(
        self,
        file_path: str,
        file_contents: str,
        sandbox_response: SandboxResponse,
        parent_fcr: FileChangeRequest | None = None,
    ) -> list[FileChangeRequest]:
        new_self = ChatGPT(chat_logger=self.chat_logger)
        new_self.messages = copy.deepcopy(self.messages)
        new_self.delete_messages_from_chat("files_to_change")
        new_self.delete_messages_from_chat("changed_files_summary")
        new_self.delete_messages_from_chat("issue_metadata")
        new_self.delete_messages_from_chat("metadata")
        new_self.messages.append(
            Message(
                content=f'<code file_path="{file_path}">\n{file_contents}\n</code>\n\n'
                + sandbox_error_prompt.format(
                    command=sandbox_response.executions[-1].command,
                    error_logs=sandbox_response.executions[-1].output,
                ),
                role="user",
            )
        )
        files_to_change_response = new_self.chat(sandbox_files_to_change_prompt)
        file_change_requests: list[FileChangeRequest] = []
        for re_match in re.finditer(
            FileChangeRequest._regex, files_to_change_response, re.DOTALL
        ):
            file_change_request = FileChangeRequest.from_string(
                re_match.group(0), parent=parent_fcr
            )
            file_change_requests.append(file_change_request)
            if file_change_request.change_type in ("modify", "create"):
                new_file_change_request = copy.deepcopy(file_change_request)
                new_file_change_request.change_type = "check"
                new_file_change_request.id_ = str(uuid.uuid4())
                new_file_change_request.parent = file_change_request
                file_change_requests.append(new_file_change_request)

        return file_change_requests

    def change_files_in_github_iterator(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str,
        blocked_dirs: list[str],
    ) -> Generator[tuple[FileChangeRequest, bool], None, None]:
        logger.debug(file_change_requests)
        completed = 0
        sandbox_execution = None
        changed_files: list[tuple[str, str]] = []

        i = 0

        file_change_requests[i].status = "running"

        while i < min(len(file_change_requests), 15):
            file_change_request = file_change_requests[i]
            logger.print(file_change_request.change_type, file_change_request.filename)
            changed_file = False

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
                            sandbox_response,
                            commit,
                            changed_files,
                        ) = self.handle_create_file_main(
                            file_change_request,
                            branch,
                            changed_files=changed_files,
                        )
                        file_change_requests[i].status = "succeeded"
                        if i + 1 < len(file_change_requests):
                            file_change_requests[i + 1].status = "running"
                        yield (
                            file_change_request,
                            changed_file,
                            sandbox_response,
                            commit,
                            file_change_requests,
                        )
                    case "modify" | "rewrite":
                        # Remove snippets from this file if they exist
                        snippet_msgs = [
                            m for m in self.messages if m.key == BOT_ANALYSIS_SUMMARY
                        ]
                        if len(snippet_msgs) > 0:  # Should always be true
                            snippet_msg = snippet_msgs[0]
                            file = re.escape(file_change_request.filename)
                            regex = rf'<snippet source="{file}:\d*-?\d*.*?<\/snippet>'
                            snippet_msg.content = re.sub(
                                regex,
                                "",
                                snippet_msg.content,
                                flags=re.DOTALL,
                            )
                        (
                            changed_file,
                            sandbox_execution,
                            commit,
                            changed_files,
                        ) = self.handle_modify_file_main(
                            file_change_request=file_change_request,
                            branch=branch,
                            changed_files=changed_files,
                        )
                        file_change_requests[i].status = (
                            "succeeded" if changed_file else "failed"
                        )
                        if i + 1 < len(file_change_requests):
                            file_change_requests[i + 1].status = "running"
                        yield (
                            file_change_request,
                            changed_file,
                            sandbox_execution,
                            commit,
                            file_change_requests,
                        )
                    case "check":
                        contents_obj = self.get_contents(
                            file_change_request.filename, branch
                        )
                        contents = contents_obj.decoded_content.decode("utf-8")
                        updated_contents, sandbox_execution = self.check_sandbox(
                            file_change_request.filename, contents, changed_files
                        )
                        if contents != updated_contents:
                            self.repo.update_file(
                                file_change_request.filename,
                                f"Sandbox run {file_change_request.filename}",
                                updated_contents,
                                sha=contents_obj.sha,
                                branch=branch,
                            )
                        if sandbox_execution.success is False:
                            additional_file_change_requests = (
                                self.get_files_to_change_from_sandbox(
                                    file_change_request.filename,
                                    updated_contents,
                                    sandbox_execution,
                                    parent_fcr=file_change_request,
                                )
                            )
                            new_check_fcr = copy.deepcopy(file_change_request)
                            new_check_fcr.status = "queued"
                            new_check_fcr.id_ = str(uuid.uuid4())
                            additional_file_change_requests.append(new_check_fcr)
                            file_change_requests = (
                                file_change_requests[: i + 1]
                                + additional_file_change_requests
                                + file_change_requests[i + 1 :]
                            )
                        file_change_requests[i].status = (
                            "succeeded" if sandbox_execution.success else "failed"
                        )
                        if i + 1 < len(file_change_requests):
                            file_change_requests[i + 1].status = "running"
                        yield (
                            file_change_request,
                            True,
                            sandbox_execution,
                            commit,
                            file_change_requests,
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
                        file_change_requests[i].status = "succeeded"
                        if i + 1 < len(file_change_requests):
                            file_change_requests[i + 1].status = "running"
                        yield file_change_request, changed_file, sandbox_execution, commit, file_change_requests
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
                        file_change_requests[i].status = "succeeded"
                        if i + 1 < len(file_change_requests):
                            file_change_requests[i + 1].status = "running"
                        yield file_change_request, changed_file, sandbox_execution, commit, file_change_requests
                    case _:
                        raise Exception(
                            f"Unknown change type {file_change_request.change_type}"
                        )
                logger.print(f"Done processing {file_change_request.filename}.")
            except MaxTokensExceeded as e:
                raise e
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(f"Error in change_files_in_github {e}")
                logger.error(traceback.format_exc())

            if changed_file:
                completed += 1
            i += 1

    def handle_create_file_main(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        changed_files: list[tuple[str, str]] = [],
    ):
        file_change, sandbox_response = self.create_file(
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

        changed_files.append((file_change_request.filename, ("", file_change.code)))

        file_change_request.new_content = file_change.code, changed_files

        return True, sandbox_response, result["commit"], changed_files

    def handle_create_file_iterator(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        changed_files: list[tuple[str, str]] = [],
    ):
        (
            file_changed,
            sandbox_response,
            commit,
            changed_files,
        ) = self.handle_create_file_main(
            file_change_request,
            branch,
            changed_files,
        )

        yield True, sandbox_response, commit, changed_files

        if not sandbox_response.success:
            new_file_change_request = file_change_request
            new_file_change_request.change_type = "modify"
            new_file_change_request.id_ = str(uuid.uuid4())
            sandbox_command = sandbox_response.executions[-1].command.format(
                file_path=file_change_request.filename
            )
            if "test" in sandbox_command:
                sandbox_prompt = sandbox_error_prompt_test
                new_file_change_request.failed_sandbox_test = True
            else:
                sandbox_prompt = sandbox_error_prompt
            new_file_change_request.instructions = sandbox_prompt.format(
                command=sandbox_command,
                error_logs=sandbox_response.executions[-1].output,
            )
            logger.warning(sandbox_response.executions[-1].output)
            for (
                new_file_contents,
                new_sandbox_execution,
                commit_message,
                changed_files,
            ) in self.handle_modify_file_iterator(
                file_change_request=new_file_change_request,
                branch=branch,
                changed_files=changed_files,
            ):
                file_change_request.new_content = new_file_contents
                yield True, new_sandbox_execution, commit_message, changed_files

    def handle_create_file(self, *args, **kwargs):
        for response in self.handle_create_file_iterator(*args, **kwargs):
            pass
        return response

    def handle_modify_file_main(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        changed_files: list[tuple[str, str]] = [],
    ):
        CHUNK_SIZE = 600  # Number of lines to process at a time
        sandbox_execution: SandboxResponse = None
        commit_message: str = None
        try:
            file = self.get_file(file_change_request.filename, branch=branch)
            file_contents = file.decoded_content.decode("utf-8")
            file_name = file_change_request.filename
            lines = file_contents.split("\n")

            if file_change_request.start_and_end_lines:
                CHUNK_SIZE = (
                    10000  # dont chunk if we know the start and end lines already
                )

            def get_new_file(temperature: float = 0.0):
                nonlocal changed_files
                new_file_contents = ""
                try:
                    chunking = (
                        len(lines) > CHUNK_SIZE
                    )  # Only chunk if the file is large enough
                    if file_change_request.entity:
                        (
                            new_file_contents,
                            suggested_commit_message,
                            sandbox_error,
                            changed_files,
                        ) = self.modify_file(
                            file_change_request,
                            contents="\n".join(lines),
                            chunking=True,
                            temperature=temperature,
                            changed_files=changed_files,
                        )
                        commit_message = suggested_commit_message
                    elif not chunking:
                        (
                            new_file_contents,
                            suggested_commit_message,
                            sandbox_error,
                            changed_files,
                        ) = self.modify_file(
                            file_change_request,
                            contents="\n".join(lines),
                            chunking=chunking,
                            changed_files=changed_files,
                            temperature=temperature,
                        )
                        commit_message = suggested_commit_message
                    elif file_change_request.comment_line is not None:
                        # find the line with the comment
                        comment_line = file_change_request.comment_line
                        expand_size = 50
                        start = max(0, comment_line - expand_size)
                        end = min(len(lines), comment_line + expand_size)
                        chunk = "\n".join(lines[start:end])
                        (
                            new_chunk,
                            commit_message,
                            sandbox_error,
                            changed_files,
                        ) = self.modify_file(
                            file_change_request,
                            contents=chunk,
                            changed_files=changed_files,
                            temperature=temperature,
                        )
                        new_lines = copy.deepcopy(lines)
                        new_lines[start:end] = new_chunk.split("\n")
                        new_file_contents = "\n".join(new_lines)
                    else:
                        chunks = chunk_code(
                            file_contents,
                            path=file_change_request.filename,
                            MAX_CHARS=15_000,
                            coalesce=5_000,
                        )
                        for i, chunk in enumerate(chunks):
                            chunk.start += 1
                            if chunk.end >= len(lines) - 2:
                                chunk.end += 1
                            chunk_contents = chunk.get_snippet(
                                add_ellipsis=False, add_lines=False
                            )
                            (
                                new_chunk,
                                suggested_commit_message,
                                sandbox_error,
                                changed_files,
                            ) = self.modify_file(
                                file_change_request,
                                contents=chunk_contents,
                                chunking=True,
                                changed_files=changed_files,
                                temperature=temperature,
                            )
                            commit_message = suggested_commit_message
                            logger.info(
                                f"Chunk {i} of {len(chunks)}: {generate_diff(chunk_contents, new_chunk)}"
                            )
                            new_file_contents += new_chunk + "\n"
                except Exception as e:
                    logger.print(e)
                    raise e
                changed_files.append((file_name, ("\n".join(lines), new_file_contents)))
                return new_file_contents, commit_message, sandbox_error, changed_files

            (
                new_file_contents,
                commit_message,
                sandbox_execution,
                changed_files,
            ) = get_new_file()

            if file_contents == new_file_contents:
                logger.info("No changes made to file. Retrying with temperature 0.2")
                (
                    new_file_contents,
                    commit_message,
                    sandbox_execution,
                    changed_files,
                ) = get_new_file(temperature=0.2)

            if file_contents == new_file_contents:
                logger.info("No changes made to file. Retrying with temperature 0.4")
                (
                    new_file_contents,
                    commit_message,
                    sandbox_execution,
                    changed_files,
                ) = get_new_file(temperature=0.4)

            # If the original file content is identical to the new file content, log a warning and return
            if file_contents == new_file_contents:
                logger.warning(
                    f"No changes made to {file_change_request.filename}. Skipping file"
                    " update."
                )
                return (
                    False,
                    sandbox_execution,
                    "No changes made to file.",
                    changed_files,
                )
            try:
                result = self.repo.update_file(
                    file_name,
                    commit_message,
                    new_file_contents,
                    file.sha,
                    branch=branch,
                )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.info(f"Error in updating file, repulling and trying again {e}")
                file = self.get_file(file_change_request.filename, branch=branch)
                result = self.repo.update_file(
                    file_name,
                    commit_message,
                    new_file_contents,
                    file.sha,
                    branch=branch,
                )
            file_change_request.new_content = new_file_contents
            return True, sandbox_execution, result["commit"], changed_files
        except MaxTokensExceeded as e:
            raise e
        except SystemExit:
            raise SystemExit
        except Exception as e:
            tb = traceback.format_exc()
            logger.info(f"Error in handle_modify_file: {tb}")
            return False, sandbox_execution, None, changed_files

    def handle_modify_file_iterator(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        changed_files: list[tuple[str, str]] = [],
    ):
        (
            file_changed,
            sandbox_response,
            commit_message,
            changed_files,
        ) = self.handle_modify_file_main(
            file_change_request=file_change_request,
            branch=branch,
            changed_files=changed_files,
        )
        yield file_changed, sandbox_response, commit_message, changed_files
        prev_sandbox_response_str = None
        prev_num_changed_files = []
        for _ in range(5):
            # if sandbox success, same response, or no changes, break
            sandbox_response_str = (
                "\n".join(sandbox_response.error_messages) if sandbox_response else ""
            )
            if (
                sandbox_response
                and sandbox_response.success
                or prev_sandbox_response_str == sandbox_response_str
                or prev_num_changed_files == len(changed_files)
            ):
                break
            if sandbox_response and not sandbox_response.success:
                new_file_change_request = file_change_request
                new_file_change_request.id_ = str(uuid.uuid4())
                sandbox_command = sandbox_response.executions[-1].command.format(
                    file_path=file_change_request.filename
                )
                if "test" in sandbox_command:
                    sandbox_prompt = sandbox_error_prompt_test
                    new_file_change_request.failed_sandbox_test = True
                else:
                    sandbox_prompt = sandbox_error_prompt
                new_file_change_request.instructions = sandbox_prompt.format(
                    command=sandbox_command,
                    error_logs=sandbox_response.executions[-1].output,
                )
                logger.warning(sandbox_response.executions[-1].output)
                (
                    file_changed,
                    sandbox_response,
                    commit_message,
                    changed_files,
                ) = self.handle_modify_file_main(
                    file_change_request=new_file_change_request,
                    branch=branch,
                    changed_files=changed_files,
                )
            prev_num_changed_files = len(changed_files)
            prev_sandbox_response_str = sandbox_response_str
            yield file_changed, sandbox_response, commit_message, changed_files

    def handle_modify_file(self, *args, **kwargs):
        for response in self.handle_modify_file_iterator(*args, **kwargs):
            pass
        return response


class ModifyBot:
    def __init__(
        self,
        additional_messages: list[Message] = [],
        chat_logger=None,
        parent_bot: SweepBot = None,
        old_file_contents: str = "",
        current_file_diff: str = "",
        **kwargs,
    ):
        self.fetch_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            fetch_snippets_system_prompt, chat_logger=chat_logger, **kwargs
        )
        self.fetch_snippets_bot.messages.extend(additional_messages)
        self.update_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            update_snippets_system_prompt, chat_logger=chat_logger, **kwargs
        )
        self.update_snippets_bot.messages.extend(additional_messages)
        self.parent_bot = parent_bot

        self.extract_leftover_comments_bot: ExtractLeftoverComments = (
            ExtractLeftoverComments(chat_logger=chat_logger, **kwargs)
        )
        self.extract_leftover_comments_bot.messages.extend(additional_messages)
        self.prune_modify_snippets_bot: PruneModifySnippets = PruneModifySnippets(
            chat_logger=chat_logger, **kwargs
        )
        self.prune_modify_snippets_bot.messages.extend(additional_messages)
        self.chat_logger = chat_logger
        self.additional_messages = additional_messages
        self.old_file_contents = old_file_contents
        self.current_file_diff = current_file_diff
        self.additional_diffs = ""

    def get_diffs_message(self, file_contents: str):
        if self.current_file_diff == "" and self.old_file_contents == file_contents:
            return self.additional_diffs
        elif self.current_file_diff == "":
            diff = generate_diff(self.old_file_contents, file_contents)
        elif self.old_file_contents == file_contents:
            diff = self.current_file_diff
        else:
            diff = (
                self.old_file_contents
                + "\n...\n"
                + generate_diff(self.old_file_contents, file_contents)
            )
        diff += self.additional_diffs
        return f"\n# Changes Made\nHere are changes we already made to this file:\n<diff>\n{diff}\n</diff>\n"

    def try_update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        (
            snippet_queries,
            extraction_terms,
            analysis_and_identification,
        ) = self.get_snippets_to_modify(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            chunking=chunking,
        )

        new_file, leftover_comments, change_validation = self.update_file(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            snippet_queries=snippet_queries,
            extraction_terms=extraction_terms,
            chunking=chunking,
            analysis_and_identification=analysis_and_identification,
        )
        for _ in range(3):
            if leftover_comments and not DEBUG:
                joined_comments = "\n".join(leftover_comments)
                new_file_change_request = copy.deepcopy(file_change_request)
                new_file_change_request.new_content = new_file
                new_file_change_request.id_ = str(uuid.uuid4())
                new_file_change_request.instructions = f"Address all of the unfinished code changes here: \n{joined_comments}"
                self.fetch_snippets_bot.messages = self.fetch_snippets_bot.messages[:-2]
                self.prune_modify_snippets_bot.messages = (
                    self.prune_modify_snippets_bot.messages[:-2]
                )
                (
                    snippet_queries,
                    extraction_terms,
                    analysis_and_identification,
                ) = self.get_snippets_to_modify(
                    file_path=file_path,
                    file_contents=new_file,
                    file_change_request=new_file_change_request,
                    chunking=chunking,
                )
                self.update_snippets_bot.messages = self.update_snippets_bot.messages[
                    :-2
                ]
                new_file, leftover_comments, change_validation = self.update_file(
                    file_path=file_path,
                    file_contents=new_file,
                    file_change_request=new_file_change_request,
                    snippet_queries=snippet_queries,
                    extraction_terms=extraction_terms,
                    chunking=chunking,
                    analysis_and_identification=analysis_and_identification,
                )
            if change_validation.additional_changes_required:
                file_change_request.new_content = new_file
                file_change_request.instructions = change_validation.additional_changes
                self.fetch_snippets_bot.messages = self.fetch_snippets_bot.messages[:-2]
                self.prune_modify_snippets_bot.messages = (
                    self.prune_modify_snippets_bot.messages[:-2]
                )
                # TODO: delete messages in the bots themselves
                (
                    snippet_queries,
                    extraction_terms,
                    analysis_and_identification,
                ) = self.get_snippets_to_modify(
                    file_path=file_path,
                    file_contents=file_contents,
                    file_change_request=file_change_request,
                    chunking=chunking,
                )
                self.update_snippets_bot.messages = self.update_snippets_bot.messages[
                    :-2
                ]
                new_file, leftover_comments, change_validation = self.update_file(
                    file_path=file_path,
                    file_contents=file_contents,
                    file_change_request=file_change_request,
                    snippet_queries=snippet_queries,
                    extraction_terms=extraction_terms,
                    chunking=chunking,
                    analysis_and_identification=analysis_and_identification,
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
                code=extract_python_span(
                    file_contents, [file_change_request.entity]
                ).content
                if file_change_request.entity
                else file_contents,
                changes_made=self.get_diffs_message(file_contents),
                file_path=file_path,
                request=file_change_request.instructions,
                chunking_message=use_chunking_message
                if chunking
                else dont_use_chunking_message,
            )
        )
        analysis_and_identification_pattern = r"<analysis_and_identification.*?>\n(?P<code>.*)\n</analysis_and_identification>"
        analysis_and_identification_match = re.search(
            analysis_and_identification_pattern, fetch_snippets_response, re.DOTALL
        )
        analysis_and_identifications_str = (
            analysis_and_identification_match.group("code").strip()
            if analysis_and_identification_match
            else ""
        )

        extraction_terms = []
        extraction_term_pattern = (
            r"<extraction_terms.*?>\n(?P<extraction_term>.*?)\n</extraction_terms>"
        )
        for extraction_term in re.findall(
            extraction_term_pattern, fetch_snippets_response, re.DOTALL
        ):
            for term in extraction_term.split("\n"):
                term = term.strip()
                if term:
                    extraction_terms.append(term)
        snippet_queries = []
        snippets_query_pattern = (
            r"<snippet_to_modify.*?>\n(?P<code>.*?)\n</snippet_to_modify>"
        )
        for code in re.findall(
            snippets_query_pattern, fetch_snippets_response, re.DOTALL
        ):
            snippet_queries.append(strip_backticks(code))

        if len(snippet_queries) == 0:
            raise UnneededEditError("No snippets found in file")
        return snippet_queries, extraction_terms, analysis_and_identifications_str

    def update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        snippet_queries: list[str],
        extraction_terms: list[str],
        chunking: bool = False,
        analysis_and_identification: str = "",
    ):
        is_python_file = file_path.strip().endswith(".py")

        best_matches = []
        for query in snippet_queries:
            if query.count("...") > 2:
                for section in split_ellipses(query):
                    match_ = find_best_match(section, file_contents)
                    if match_.score > 50:
                        best_matches.append(match_)
            else:
                match_ = find_best_match(query, file_contents)
                if match_.score > 50:
                    best_matches.append(match_)

        code_tree = CodeTree.from_code(file_contents) if is_python_file else None
        for i, line in enumerate(file_contents.split("\n")):
            for keyword in extraction_terms:
                if keyword in line:
                    try:
                        if is_python_file:
                            start_line, end_line = code_tree.get_lines_surrounding(i)
                        else:
                            start_line, end_line = i, i
                    except Exception as e:
                        logger.error(e)
                        start_line, end_line = i, i
                    best_matches.append(
                        Match(
                            start=start_line,
                            end=end_line + 1,
                            score=100,
                        )
                    )

        # Get all line matches where the keyword is either mentioned or used as a function call
        for keyword in extraction_terms:
            keyword = keyword.rstrip("()")
            for start, end in find_function_calls(keyword, file_contents):
                best_matches.append(
                    Match(
                        start=start,
                        end=end + 1,
                        score=100,
                    )
                )
        # get first 10 lines for imports
        IMPORT_LINES = 10
        best_matches.append(
            Match(
                start=0,
                end=min(IMPORT_LINES, len(file_contents.split("\n"))),
                score=100,
            )
        )

        if len(best_matches) == 0:
            raise UnneededEditError("No matches found in file")

        # Todo: check multiple files for matches using PR changed files

        best_matches.sort(key=lambda x: x.start + x.end * 0.00001)

        def fuse_matches(a: Match, b: Match) -> Match:
            return Match(
                start=min(a.start, b.start),
                end=max(a.end, b.end),
                score=min(a.score, b.score),
            )

        current_match = best_matches[0]
        deduped_matches: list[Match] = []

        # Fuse & dedup
        FUSE_OFFSET = 5
        for next_match_ in best_matches[1:]:
            if (
                current_match.end > next_match_.start
                or abs(current_match.end - next_match_.start) <= FUSE_OFFSET
            ):
                current_match = fuse_matches(current_match, next_match_)
            else:
                deduped_matches.append(current_match)
                current_match = next_match_
        deduped_matches.append(current_match)
        if is_python_file:
            new_deduped_matches = []
            for match_ in deduped_matches:
                start_line = code_tree.get_lines_surrounding(match_.start)[0]
                end_line = code_tree.get_lines_surrounding(match_.end)[1]
                new_deduped_matches.append(
                    Match(
                        start=start_line,
                        end=end_line + 1,
                        score=match_.score,
                    )
                )
            deduped_matches = new_deduped_matches

        selected_snippets = []
        file_contents_lines = file_contents.split("\n")
        for match_ in deduped_matches:
            current_contents = "\n".join(file_contents_lines[match_.start : match_.end])
            selected_snippets.append(current_contents)

        update_snippets_code = file_contents
        if file_change_request.entity:
            update_snippets_code = extract_python_span(
                file_contents, [file_change_request.entity]
            ).content

        if len(selected_snippets) > 1:
            indices_to_keep = self.prune_modify_snippets_bot.prune_modify_snippets(
                snippets="\n\n".join(
                    [
                        f'<snippet index="{i}">\n{snippet}\n</snippet>'
                        for i, snippet in enumerate(selected_snippets)
                    ]
                ),
                file_path=file_path,
                changes_made=self.get_diffs_message(file_contents),
                old_code=update_snippets_code,
                request=file_change_request.instructions
                + "\n"
                + analysis_and_identification,
            )
        else:
            indices_to_keep = [0]

        if len(indices_to_keep) == 0:
            raise UnneededEditError("No snippets selected")

        pruned_snippets = []
        for idx, snippet in enumerate(selected_snippets):
            if idx in indices_to_keep:
                pruned_snippets.append(snippet)
        selected_snippets = pruned_snippets

        if is_python_file:
            self.update_snippets_bot.messages[
                0
            ].content = update_snippets_system_prompt_python

        if file_change_request.failed_sandbox_test:
            update_prompt = update_snippets_prompt_test
        else:
            update_prompt = update_snippets_prompt
        update_snippets_response = self.update_snippets_bot.chat(
            update_prompt.format(
                code=update_snippets_code,
                file_path=file_path,
                snippets="\n\n".join(
                    [
                        f'<snippet index="{i}">\n{snippet}\n</snippet>'
                        for i, snippet in enumerate(selected_snippets)
                    ]
                ),
                request=file_change_request.instructions
                + "\n"
                + analysis_and_identification,
                n=len(selected_snippets),
                changes_made=self.get_diffs_message(file_contents),
            )
        )
        updated_snippets: dict[int, str] = {}
        updated_pattern = r"<<<<<<<\s+ORIGINAL\s+\(index=(?P<index>\d+)\)(?P<original_code>.*?)=======(?P<updated_code>.*?)>>>>>>>\s+UPDATED"

        if (
            len(list(re.finditer(updated_pattern, update_snippets_response, re.DOTALL)))
            == 0
        ):
            raise UnneededEditError("No snippets edited")

        for match_ in re.finditer(updated_pattern, update_snippets_response, re.DOTALL):
            index = int(match_.group("index"))
            original_code = match_.group("original_code").strip("\n")
            updated_code = match_.group("updated_code").strip("\n")

            current_contents = selected_snippets[index]
            if index not in updated_snippets:
                updated_snippets[index] = current_contents
            else:
                current_contents = updated_snippets[index]
            updated_snippets[index] = "\n".join(
                sliding_window_replacement(
                    original=current_contents.splitlines(),
                    search=original_code.splitlines(),
                    replace=updated_code.splitlines(),
                )[0]
            )

        change_validator = ChangeValidator.create(
            file_contents,
            file_change_request,
            selected_snippets,
            updated_snippets,
            chat_logger=self.chat_logger,
            additional_messages=self.additional_messages,
        )
        change_validation = ChangeValidation(
            analysis="",
            additional_changes="",
            additional_changes_required_raw="no",
            diffs_to_revert_raw="",
        )
        result = change_validator.apply_validated_changes(change_validation)

        new_code = []
        for idx, search in enumerate(selected_snippets):
            if idx not in updated_snippets:
                continue
            if selected_snippets.index(search) not in change_validator.updated_snippets:
                continue
            replace = change_validator.updated_snippets[selected_snippets.index(search)]
            new_code.append(replace)

        ending_newlines = len(file_contents) - len(file_contents.rstrip("\n"))
        result = result.rstrip("\n") + "\n" * ending_newlines

        new_code = "\n".join(new_code)
        leftover_comments = (
            (
                self.extract_leftover_comments_bot.extract_leftover_comments(
                    new_code,
                    file_path,
                    file_change_request.instructions,
                )
            )
            if not DEBUG
            else []
        )

        return result, leftover_comments, change_validation


if __name__ == "__main__":
    response = """
```python
```"""
    stripped = strip_backticks(response)
    print(stripped)
