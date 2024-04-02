import base64
import copy
import re
import time
import traceback
from typing import Dict, Generator

from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel

from sweepai.agents.complete_code import ExtractLeftoverComments
from sweepai.agents.modify_file import modify_file
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DEBUG, DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import (
    AssistantRaisedException,
    FileChangeRequest,
    FileCreation,
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
    create_file_prompt,
    files_to_change_prompt,
    pull_request_prompt,
    subissues_prompt,
    files_to_change_system_prompt
)
from sweepai.utils.autoimport import add_auto_imports
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.diff import format_contents, is_markdown
from sweepai.utils.progress import (
    AssistantAPIMessage,
    AssistantConversation,
    TicketProgress,
)
from sweepai.utils.str_utils import get_hash
from sweepai.utils.utils import check_syntax, chunk_code
from sweepai.utils.github_utils import commit_multi_file_changes

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"


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
        self, is_python_issue: bool, retries=1, pr_diffs: str | None = None
    ) -> tuple[list[FileChangeRequest], str]:
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
                if file_change_request.change_type in ("modify", "create"):
                    new_file_change_request = copy.deepcopy(file_change_request)
                    new_file_change_request.change_type = "check"
                    new_file_change_request.instructions = ""
                    new_file_change_request.parent = file_change_request
                    file_change_requests.append(new_file_change_request)

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

    def create_file(
        self,
        file_change_request: FileChangeRequest,
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] | None = None,
    ):
        file_change: FileCreation | None = None
        key = f"file_change_created_{file_change_request.filename}"
        old_messages = self.messages
        self.delete_messages_from_chat(key_to_delete="files_to_change")
        blocked_dirs = get_blocked_dirs(self.repo)
        if file_change_request.relevant_files:
            relevant_files_contents = []
            for file_path in file_change_request.relevant_files:
                if is_blocked(file_path, blocked_dirs)["success"]:
                    continue
                try:
                    relevant_files_contents.append(
                        safe_decode(
                            self.repo,
                            file_path,
                            ref=self.cloned_repo.branch
                        )
                    )
                except Exception:
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
        try:
            create_file_response = self.chat_anthropic(
                create_file_prompt.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                ),
                message_key=key,
                model="claude-3-opus-20240229"
            )
        except Exception as e:
            create_file_response = self.chat(
                create_file_prompt.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                ),
                message_key=key,
            )
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
        # new file has been created
        file_original_snippets = chunk_code(file_change.code, file_change_request.filename, 1400, 500)
        view_file_contents_lines = file_change.code.split("\n")
        file_chunks = [
            "\n".join(view_file_contents_lines[max(snippet.start - 1, 0) : snippet.end])
            for snippet in file_original_snippets
        ]
        file_content_changes = {file_change_request.filename: {"contents": file_change.code, "original_contents": "", "chunks": file_chunks}}
        # possible we need to do more changes
        if leftover_comments and not DEBUG:
            file_contents = file_change.code
            new_fcr = copy.deepcopy(file_change_request)
            joined_comments = "\n".join(leftover_comments)
            new_fcr.instructions = (
                f"Address all of the unfinished code changes here: \n{joined_comments}"
            )
            (
                file_content_changes,
                _,
                _,
            ) = self.modify_file(
                new_fcr,
                contents=file_contents,
                previous_modify_files_dict=previous_modify_files_dict,
            )
            # get the new file, there may be other files modified but are currently dropped, not yet implemented
            file_contents = file_content_changes[file_change_request.filename]['contents']
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
            self.check_completion(  # use async
                file_change_request.filename, file_change.code
            )
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(f"Error: {e}")

        sandbox_execution = None

        self.messages = old_messages

        file_change.code = add_auto_imports(
            file_change_request.filename,
            self.cloned_repo.repo_dir,
            file_change.code,
        )

        return file_change, sandbox_execution, file_content_changes

    def modify_file(
        self,
        file_change_request: FileChangeRequest,
        contents: str = "",
        chunking: bool = False,
        branch: str = None,
        temperature: float = 0.1,
        assistant_conversation: AssistantConversation | None = None,
        additional_messages: list[Message] = [],
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] = None,
    ):
        new_files = modify_file(
            self.cloned_repo,
            self.human_message.get_issue_metadata(),
            file_change_request,
            contents,
            branch,
            self.comment_pr_diff_str,
            assistant_conversation,
            self.ticket_progress,
            self.chat_logger,
            additional_messages=additional_messages,
            previous_modify_files_dict=previous_modify_files_dict,
        )
        commit_message = f"feat: Updated {file_change_request.filename}"[:50]
        return new_files, commit_message, None

    def change_files_in_github_iterator(
        self,
        file_change_requests: list[FileChangeRequest],
        branch: str,
        blocked_dirs: list[str],
        additional_messages: list[Message] = []
    ) -> Generator[tuple[FileChangeRequest, bool], None, None]:
        completed = 0
        sandbox_response = None
        commit_messages = {
            "create": "Created new file",
            "modify": "Modified existing file",
            "rewrite": "Rewrote existing file",
            "check": "Checked file",
            "delete": "Deleted file",
            "rename": "Renamed file",
        }

        i = 0

        file_change_requests[i].status = "running"
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] | None = None
        while i < min(len(file_change_requests), 20):
            file_change_request = file_change_requests[i]
            logger.print(file_change_request.change_type, file_change_request.filename)
            changed_file = False

            if self.ticket_progress:
                self.ticket_progress.coding_progress.file_change_requests = (
                    file_change_requests
                )
                self.ticket_progress.save()

            try:
                commit = commit_messages.get(
                    file_change_request.change_type, "No commit message provided"
                )
                if is_blocked(file_change_request.filename, blocked_dirs)["success"]:
                    logger.print(
                        f"Skipping {file_change_request.filename} because it is blocked."
                    )
                    i += 1
                    continue

                logger.print(
                    f"Processing {file_change_request.filename} for change type"
                    f" {file_change_request.change_type}..."
                )

                first_chars_in_instructions = file_change_request.instructions.lower()
                first_chars_in_instructions = first_chars_in_instructions[
                    : min(60, len(first_chars_in_instructions))
                ]
                # add context on which fcr it is currently on and how many are left
                all_fcrs_strings = ", ".join(file_change_request.relevant_files)
                current_fcr_strings = f"To solve the user's request you will modify/create the following {len(file_change_request.relevant_files)} files: {all_fcrs_strings}. You are currently modifying {file_change_request.filename}!"
                additional_messages += [
                    Message(
                        role="user",
                        content=current_fcr_strings,
                        key="instructions",
                    )
                ]
                match file_change_request.change_type:
                    case "create":
                        (
                            changed_file,
                            sandbox_response,
                            commit,
                            new_file_contents
                        ) = self.handle_create_file_main(
                            file_change_request,
                            branch,
                            previous_modify_files_dict=previous_modify_files_dict,
                        )
                        # update previous_modify_files_dict
                        if not previous_modify_files_dict:
                            previous_modify_files_dict = {}
                        if new_file_contents:
                            for key, value in new_file_contents.items():
                                previous_modify_files_dict[key] = value
                        file_change_requests[i].status = "succeeded"
                        file_change_requests[i].commit_hash_url = commit.html_url
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
                        if self.ticket_progress is not None:
                            for _ in range(
                                len(
                                    self.ticket_progress.coding_progress.assistant_conversations
                                ),
                                i + 1,
                            ):
                                self.ticket_progress.coding_progress.assistant_conversations.append(
                                    AssistantConversation()
                                )
                        (
                            changed_file,
                            sandbox_response,
                            commit,
                            new_file_contents
                        ) = self.handle_modify_file_main(
                            file_change_request=file_change_request,
                            branch=branch,
                            assistant_conversation=(
                                self.ticket_progress.coding_progress.assistant_conversations[
                                    i
                                ]
                                if self.ticket_progress
                                else None
                            ),
                            additional_messages=additional_messages,
                            previous_modify_files_dict=previous_modify_files_dict,
                        )
                        # update previous_modify_files_dict
                        if not previous_modify_files_dict:
                            previous_modify_files_dict = {}
                        if new_file_contents:
                            for key, value in new_file_contents.items():
                                previous_modify_files_dict[key] = value
                        file_change_requests[i].status = (
                            "succeeded" if changed_file else "failed"
                        )
                        file_change_requests[i].commit_hash_url = (
                            commit.html_url
                            if commit and not isinstance(commit, str)
                            else None  # fix later
                        )
                        if i + 1 < len(file_change_requests):
                            file_change_requests[i + 1].status = "running"
                        yield (
                            file_change_request,
                            changed_file,
                            sandbox_response,
                            commit,
                            file_change_requests,
                        )
                    case "check":
                        if file_change_requests[i - 1].status == "failed":
                            file_change_request.status = "failed"
                            yield (
                                file_change_request,
                                False,
                                None,
                                None,
                                file_change_requests,
                            )
                        else:
                            commit_hash = self.repo.get_branch(branch=branch).commit.sha
                            check_runs = list(
                                self.repo.get_commit(commit_hash).get_check_runs()
                            )
                            completed = True
                            total_wait_time = 3600
                            sleep_time = 5
                            for j in range(total_wait_time // sleep_time):
                                if j % 4 == 0:
                                    commit_hash_url = f'<a href="https://github.com/{self.repo.full_name}/commit/{commit_hash}">{commit_hash}</a>'
                                    additional_instructions = ""
                                    conclusions = []
                                    check_runs = list(
                                        self.repo.get_commit(
                                            commit_hash
                                        ).get_check_runs()
                                    )
                                    for check_run in check_runs:
                                        conclusions.append(check_run.conclusion)
                                        conclusion_str = (
                                            "✓"
                                            if check_run.conclusion == "success"
                                            else (
                                                "✗"
                                                if check_run.conclusion == "failure"
                                                else "⋯"
                                            )
                                        )
                                        additional_instructions += f'• {check_run.name}: <a href="{check_run.html_url}">{conclusion_str}</a>\n'
                                    # these are distinct, it's None if it's not done so succeeded and failed can both be false
                                    succeeded = all(
                                        conclusion == "success"
                                        for conclusion in conclusions
                                    )
                                    failed = any(
                                        conclusion == "failure"
                                        for conclusion in conclusions
                                    )
                                    waiting = any(
                                        conclusion is None for conclusion in conclusions
                                    )
                                    if succeeded:
                                        file_change_request.status = "succeeded"
                                    elif failed:
                                        file_change_request.status = "failed"
                                    file_change_request.instructions = f"\nRan GitHub Actions for {commit_hash_url}:\n{additional_instructions}"
                                    yield (
                                        file_change_request,
                                        True,
                                        None,
                                        None,
                                        file_change_requests,
                                    )
                                    if not waiting or failed or succeeded:
                                        break
                                time.sleep(sleep_time)
                                logger.info("Waiting for check runs to complete")
                            else:
                                logger.error("Check runs did not complete in time")
                                completed = False

                            if not completed:
                                file_change_request.status = "succeeded"
                                file_change_request.instructions += "\n\nCheck runs did not complete in 60 minutes, skipping the rest."
                                yield (
                                    file_change_request,
                                    False,
                                    None,
                                    None,
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
                        yield file_change_request, changed_file, sandbox_response, commit, file_change_requests
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
                            safe_decode(
                                self.repo,
                                file_change_request.filename,
                                ref=branch
                            ),
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
                        yield file_change_request, changed_file, sandbox_response, commit, file_change_requests
                    case _:
                        raise Exception(
                            f"Unknown change type {file_change_request.change_type}"
                        )
                logger.print(f"Done processing {file_change_request.filename}.")
            except AssistantRaisedException as e:
                raise e
            except Exception as e:
                logger.error(f"Error in change_files_in_github {e}")
                logger.error(traceback.format_exc())
                discord_log_error(traceback.format_exc() + "\n" + str(e))
                file_change_request.status = "failed"

            if self.ticket_progress:
                self.ticket_progress.coding_progress.file_change_requests = (
                    file_change_requests
                )
                self.ticket_progress.save()

            if changed_file:
                completed += 1
            i += 1

    def handle_create_file_main(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] | None = None,
    ):
        file_change, sandbox_response, new_file_contents = self.create_file(
            file_change_request, previous_modify_files_dict=previous_modify_files_dict
        )
        file_markdown = is_markdown(file_change_request.filename)
        file_change.code = format_contents(file_change.code, file_markdown)
        logger.debug(
            f"{file_change_request.filename},"
            f" {f'Create {file_change_request.filename}'}, {file_change.code},"
            f" {branch}"
        )
        if new_file_contents:
            new_file_contents_to_commit = {file_path: file_data["contents"] for file_path, file_data in new_file_contents.items()}
            result = commit_multi_file_changes(self.repo, new_file_contents_to_commit, file_change.commit_message, branch)

        # file_change_request.new_content = file_change.code
        file_change_request.new_content = file_change.code

        return True, sandbox_response, result, new_file_contents

    def handle_modify_file_main(
        self,
        file_change_request: FileChangeRequest,
        branch: str,
        assistant_conversation: AssistantConversation | None = None,
        additional_messages: list[Message] = [],
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] = None,
    ):
        CHUNK_SIZE = 10000  # Disable chunking for now
        sandbox_execution: SandboxResponse = None
        commit_message: str = None
        try:
            file_contents = safe_decode(
                self.repo,
                file_change_request.filename,
                ref=branch
            )
            lines = file_contents.split("\n")

            if file_change_request.start_and_end_lines:
                CHUNK_SIZE = (
                    10000  # dont chunk if we know the start and end lines already
                )

            def get_new_file(temperature: float = 0.0):
                new_file_contents = ""
                try:
                    chunking = (
                        len(lines) > CHUNK_SIZE
                    )  # Only chunk if the file is large enough
                    sandbox_error = None
                    first_characters_in_instructions = (
                        file_change_request.instructions.lower()
                    )
                    first_characters_in_instructions = first_characters_in_instructions[
                        : min(60, len(first_characters_in_instructions))
                    ]
                    if file_change_request.entity:
                        (
                            new_file_contents,
                            suggested_commit_message,
                            sandbox_error,
                        ) = self.modify_file(
                            file_change_request,
                            contents="\n".join(lines),
                            chunking=True,
                            temperature=temperature,
                            assistant_conversation=assistant_conversation,
                            additional_messages=additional_messages,
                            previous_modify_files_dict=previous_modify_files_dict,
                        )
                        commit_message = suggested_commit_message
                    elif not chunking:
                        (
                            new_file_contents,
                            suggested_commit_message,
                            sandbox_error,
                        ) = self.modify_file(
                            file_change_request,
                            contents="\n".join(lines),
                            chunking=chunking,
                            temperature=temperature,
                            assistant_conversation=assistant_conversation,
                            additional_messages=additional_messages,
                            previous_modify_files_dict=previous_modify_files_dict,
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
                            new_file_contents,
                            suggested_commit_message,
                            sandbox_error,
                        ) = self.modify_file(
                            file_change_request,
                            contents=chunk,
                            temperature=temperature,
                            additional_messages=additional_messages,
                            previous_modify_files_dict=previous_modify_files_dict,
                        )
                        commit_message = suggested_commit_message
                    else:
                        chunks = chunk_code(
                            file_contents,
                            path=file_change_request.filename,
                            MAX_CHARS=15_000,
                            coalesce=5_000,
                        )
                        for _, chunk in enumerate(chunks):
                            chunk.start += 1
                            if chunk.end >= len(lines) - 2:
                                chunk.end += 1
                            chunk_contents = chunk.get_snippet(
                                add_ellipsis=False, add_lines=False
                            )
                            (
                                new_file_contents,
                                suggested_commit_message,
                                sandbox_error,
                            ) = self.modify_file(
                                file_change_request,
                                contents=chunk_contents,
                                chunking=True,
                                temperature=temperature,
                                additional_messages=additional_messages,
                                previous_modify_files_dict=previous_modify_files_dict,
                            )
                            commit_message = suggested_commit_message
                except Exception as e:
                    logger.print(e)
                    raise e

                return new_file_contents, commit_message, sandbox_error

            (
                new_file_contents,
                commit_message,
                sandbox_execution,
            ) = get_new_file()

            # if file_contents == new_file_contents:
            #     logger.info("No changes made to file. Retrying with temperature 0.2")
            #     (
            #         new_file_contents,
            #         commit_message,
            #         sandbox_execution,
            #     ) = get_new_file(temperature=0.2)

            # if file_contents == new_file_contents:
            #     logger.info("No changes made to file. Retrying with temperature 0.4")
            #     (
            #         new_file_contents,
            #         commit_message,
            #         sandbox_execution,
            #     ) = get_new_file(temperature=0.4)

            # If no files were updated, log a warning and return
            if not new_file_contents:
                logger.warning(
                    f"No changes made to {file_change_request.filename} or any other file. Skipping file"
                    " update."
                )
                return (
                    False,
                    sandbox_execution,
                    f"No changes made to file {file_change_request.filename} or any other file.",
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
            if file_change_request.filename in new_file_contents:
                file_change_request.new_content = new_file_contents[file_change_request.filename]["contents"]
            else:
                file_change_request.new_content = file_change_request.old_content
            return True, sandbox_execution, result, new_file_contents
        except (MaxTokensExceeded, AssistantRaisedException) as e:
            raise e
        except Exception:
            tb = traceback.format_exc()
            logger.info(f"Error in handle_modify_file: {tb}")
            return False, sandbox_execution, None, new_file_contents
