from dataclasses import field
import traceback
import re
import requests
from typing import Generator, Any, Dict
from logn import logger

from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from github.Commit import Commit
from pydantic import BaseModel

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
)
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DB_MODAL_INST_NAME, SANDBOX_URL, SECONDARY_MODEL
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.diff import (
    format_contents,
    generate_new_file_from_patch,
    is_markdown,
    get_matches,
)
from sweepai.utils.utils import chunk_code

USING_DIFF = True

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"


def strip_backticks(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s[s.find("\n") :]
    if s.endswith("```"):
        s = s[: s.rfind("\n")]
    return s


class ModifyBot:
    def __init__(self, chat_logger=None):
        self.fetch_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            fetch_snippets_system_prompt, chat_logger=chat_logger
        )
        self.update_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            update_snippets_system_prompt, chat_logger=chat_logger
        )

    def update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
    ):
        fetch_snippets_response = self.fetch_snippets_bot.chat(
            fetch_snippets_prompt.format(
                code=file_contents,
                file_path=file_path,
                request=file_change_request.instructions,
            )
        )

        snippets = []
        pattern = r"<snippet>(?P<code>.*)</snippet>"
        for code in re.findall(pattern, fetch_snippets_response, re.DOTALL):
            snippets.append(strip_backticks(code))

        update_snippets_response = self.update_snippets_bot.chat(
            update_snippets_prompt.format(
                code=file_contents,
                file_path=file_path,
                snippets=fetch_snippets_response,
                request=file_change_request.instructions,
            )
        )

        updated_snippets = []
        pattern = r"<updated_snippet id=\"(?P<id>.*)\">(?P<code>.*)</updated_snippet>"
        for _id, code in re.findall(pattern, update_snippets_response, re.DOTALL):
            updated_snippets.append(strip_backticks(code))

        replace_prompt = """"""

        for search, replace in zip(snippets, updated_snippets):
            replace_prompt += f"""
<<<< ORIGINAL
{search}
====
{replace}
>>>> UPDATED
"""

        print("REPLACE PROMPT")
        print(len(replace_prompt))
        print(len(updated_snippets))
        print(replace_prompt)

        updated_code, _ = generate_new_file_from_patch(
            replace_prompt,
            file_contents,
        )

        return updated_code


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
                snippet.expand(15)
                snippets.append(snippet)

            self.populate_snippets(snippets)
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

    def get_files_to_change(self, retries=1) -> tuple[list[FileChangeRequest], str]:
        file_change_requests: list[FileChangeRequest] = []
        # Todo: put retries into a constants file
        # also, this retries multiple times as the calls for this function are in a for loop

        for count in range(retries):
            try:
                logger.info(f"Generating for the {count}th time...")
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
                continue
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
        return file_change_requests


class SweepBot(CodeGenBot, GithubBot):
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

    def create_file(self, file_change_request: FileChangeRequest):
        file_change: FileCreation | None = None
        key = f"file_change_created_{file_change_request.filename}"
        create_file_response = self.chat(
            create_file_prompt.format(
                filename=file_change_request.filename,
                instructions=file_change_request.instructions,
            ),
            message_key=key,
        )
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
    ):
        key = f"file_change_modified_{file_change_request.filename}"
        file_markdown = is_markdown(file_change_request.filename)
        # TODO(sweep): edge case at empty file
        line_count = contents.count("\n") + 1
        message = modify_file_prompt_3.format(
            filename=file_change_request.filename,
            instructions=file_change_request.instructions,
            code=contents_line_numbers,
            line_count=line_count,
        )
        recreate_file = False
        old_system_message = self.messages[0].content
        try:
            if chunking:
                # TODO (sweep): make chunking / streaming better
                message = chunking_prompt + message
                old_system_message = self.messages[0].content
                self.messages[0].content = modify_file_system_message
                modify_file_response = self.chat(
                    message
                    + "\nIf you do not wish to make changes to this file, please type `skip`.",
                    message_key=key,
                )
                self.delete_messages_from_chat(key)
                self.messages[0].content = old_system_message
            else:
                if line_count < RECREATE_LINE_LENGTH:
                    message = modify_recreate_file_prompt_3.format(
                        filename=file_change_request.filename,
                        instructions=file_change_request.instructions,
                        code=contents_line_numbers,
                        line_count=line_count,
                    )

                    self.messages[0].content = modify_recreate_file_system_message
                    modify_file_response = self.chat(
                        message,
                        message_key=key,
                    )
                    recreate_file = True
                    self.messages[0].content = old_system_message
                else:
                    self.messages[0].content = modify_file_system_message
                    modify_file_response = self.chat(
                        message,
                        message_key=key,
                    )
                    self.messages[0].content = old_system_message
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
            logger.info(
                f"generate_new_file with contents: {contents} and"
                f" modify_file_response: {modify_file_response}"
            )
            if recreate_file:
                # Todo(lukejagg): Discord logging on error
                new_file = re.findall(
                    r"<new_file>\n(.*?)\n?</new_file>", modify_file_response, re.DOTALL
                )[0]
            else:
                new_file, errors = generate_new_file_from_patch(
                    modify_file_response,
                    contents,
                    chunk_offset=chunk_offset,
                    sweep_context=self.sweep_context,
                )
                if errors:
                    logger.error(errors)

            try:
                for _, replace in get_matches(modify_file_response):
                    implemented = self.check_completion(  # can use async
                        file_change_request.filename, replace
                    )
                    if not implemented:
                        discord_log_error(
                            f"{self.sweep_context.issue_url}\nUnimplemented Modify Section: {'gpt3.5' if self.sweep_context.use_faster_model else 'gpt4'}: \n",
                            priority=2 if self.sweep_context.use_faster_model else 0,
                        )
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(f"Error: {e}")

            new_file = format_contents(new_file, file_markdown)

            commit_message_match = re.search(
                'Commit message: "(?P<commit_message>.*)"', modify_file_response
            )
            if commit_message_match:
                commit_message = commit_message_match.group("commit_message")
            else:
                commit_message = f"Updated {file_change_request.filename}"
            commit_message = commit_message[: min(len(commit_message), 50)]

            sandbox_execution = None
            if not chunking:
                new_file, sandbox_execution = self.check_sandbox(
                    file_change_request.filename, new_file
                )
            return new_file, commit_message, sandbox_execution
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
        num_fcr = len(file_change_requests)
        completed = 0
        sandbox_execution = None

        added_modify_hallucination = False

        for file_change_request in file_change_requests:
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
                            sandbox_execution,
                            commit,
                        ) = self.handle_create_file(
                            file_change_request, branch, sandbox=sandbox
                        )
                    case "modify":
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

                        (
                            changed_file,
                            sandbox_execution,
                            commit,
                        ) = self.handle_modify_file(
                            file_change_request, branch, sandbox=sandbox
                        )
                    case "rewrite":
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

                        changed_file, sandbox_execution = self.rewrite_file(
                            file_change_request, branch
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
        self, file_change_request: FileChangeRequest, branch: str, sandbox=None
    ) -> tuple[bool, None, Commit]:
        try:
            file_change, sandbox_execution = self.create_file(file_change_request)
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
    ) -> tuple[str, Any, Commit]:
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
                # 600,
                400,
                # 300,
            ]  # Define the chunk sizes for the backoff mechanism
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
                return False, sandbox_error, "No changes made to file."
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
                return True, sandbox_error, result["commit"]
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
                return True, sandbox_error, result["commit"]
        except MaxTokensExceeded as e:
            raise e
        except SystemExit:
            raise SystemExit
        except Exception as e:
            tb = traceback.format_exc()
            logger.info(f"Error in handle_modify_file: {tb}")
            return False, sandbox_error, None
