import asyncio
import traceback
import re

import modal
from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel

from sweepai.core.chat import ChatGPT
from sweepai.core.edit_chunk import EditBot
from sweepai.core.entities import (
    FileCreation,
    ProposedIssue,
    FileChangeRequest,
    PullRequest,
    RegexMatchError,
    Snippet,
    NoFilesException,
    Message,
    MaxTokensExceeded,
)
from sweepai.core.prompts import (
    files_to_change_prompt,
    subissues_prompt,
    pull_request_prompt,
    create_file_prompt,
    modify_file_hallucination_prompt,
    modify_file_prompt_3,
    code_repair_modify_prompt,
    snippet_replacement,
    chunking_prompt,
)
from sweepai.config.client import SweepConfig, get_blocked_dirs
from sweepai.config.server import DB_MODAL_INST_NAME, SECONDARY_MODEL
from sweepai.utils.diff import (
    format_contents,
    generate_new_file_from_patch,
    is_markdown,
)

USING_DIFF = True

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"


class CodeGenBot(ChatGPT):
    def summarize_snippets(self, content: str = ""):
        snippet_summarization = self.chat(
            snippet_replacement,
            message_key="snippet_summarization",
        )  # maybe add relevant info
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
                        f"Error in summarize_snippets: {raw_snippet}. Likely failed to parse"
                    )
                file_path, lines = raw_snippet.split(":", 1)
                if "-" not in lines:
                    logger.warning(
                        f"Error in summarize_snippets: {raw_snippet}. Likely failed to parse"
                    )
                start, end = lines.split("-", 1)
                start = int(start)
                end = int(end)
                end = min(end, start + 200)

                snippet = Snippet(file_path=file_path, start=start, end=end, content="")
                snippet.expand(15)
                snippets.append(snippet)

            self.populate_snippets(snippets)
            snippets_text = "\n".join([snippet.xml for snippet in snippets])
        except Exception as e:
            logger.warning(f"Error in summarize_snippets: {e}. Likely failed to parse")
            snippets_text = self.get_message_content_from_message_key(
                ("relevant_snippets")
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

    def get_files_to_change(self, retries=1):
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
                print(e)
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

            pull_request.branch_name = "sweep/" + final_branch
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
        except Exception:
            return False

    def clean_branch_name(self, branch: str) -> str:
        # Replace invalid characters with underscores
        branch = re.sub(r"[^a-zA-Z0-9_\-/]", "_", branch)

        # Remove consecutive underscores
        branch = re.sub(r"_+", "_", branch)

        # Remove leading or trailing underscores
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
                for i in range(1, 16):
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
            except Exception as e:
                logger.error(snippet)

    def search_snippets(
        self,
        query: str,
        installation_id: str,
        num_snippets: int = 30,
    ) -> list[Snippet]:
        get_relevant_snippets = modal.Function.lookup(
            DB_MODAL_INST_NAME, "get_relevant_snippets"
        )
        snippets: list[Snippet] = get_relevant_snippets.call(
            self.repo.full_name,
            query=query,
            n_results=num_snippets,
            installation_id=installation_id,
        )
        self.populate_snippets(snippets)
        return snippets

    @staticmethod
    def is_blocked(file_path: str, blocked_dirs: list[str]):
        for blocked_dir in blocked_dirs:
            if file_path.startswith(blocked_dir) and len(blocked_dir) > 0:
                return {"success": True, "path": blocked_dir}
        return {"success": False}

    def validate_file_change_requests(
        self, file_change_requests: list[ProposedIssue], branch: str = ""
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
                    file_change_request.instructions = f'❌ Unable to modify files in `{block_status["path"]}`\nEdit `sweep.yaml` to configure.'
            except Exception as e:
                logger.info(traceback.format_exc())
        return file_change_requests


class SweepBot(CodeGenBot, GithubBot):
    def create_file(self, file_change_request: ProposedIssue) -> FileCreation:
        file_change: FileCreation | None = None
        key = f"file_change_created_{file_change_request.filename}"
        create_file_response = self.chat(
            create_file_prompt.format(
                filename=file_change_request.filename,
                instructions=file_change_request.instructions,
                # commit_message=f"Create {file_change_request.filename}"
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

            new_diffs = self.chat(
                code_repair_modify_prompt.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                    code=file_change.code,
                    diff="",
                ),
                message_key=key + "-validation",
            )
            final_file, errors = generate_new_file_from_patch(
                new_diffs, file_change.code, sweep_context=self.sweep_context
            )

            final_file = format_contents(
                final_file, is_markdown(file_change_request.filename)
            )
            final_file += "\n"
            file_change.code = final_file
            logger.info("Done validating file change request")

            return file_change
        except Exception as e:
            # Todo: should we undo appending to file_change_paths?
            logger.warning(e)
            logger.warning(f"Failed to parse. Retrying for the 1st time...")
            self.delete_messages_from_chat(key)
        raise Exception("Failed to parse response after 5 attempts.")

    def modify_file(
        self,
        file_change_request: ProposedIssue,
        contents: str = "",
        contents_line_numbers: str = "",
        branch=None,
        chunking: bool = False,
        chunk_offset: int = 0,
        retries: int = 1,
    ) -> tuple[str, str]:
        for count in range(retries):
            key = f"file_change_modified_{file_change_request.filename}"
            file_markdown = is_markdown(file_change_request.filename)
            # TODO(sweep): edge case at empty file
            message = modify_file_prompt_3.format(
                filename=file_change_request.filename,
                instructions=file_change_request.instructions,
                code=contents_line_numbers,
                line_count=contents.count("\n") + 1,
            )
            try:
                if chunking:
                    # TODO (sweep): make chunking / streaming better
                    message = chunking_prompt + message
                    modify_file_response = self.chat(
                        message,
                        message_key=key,
                    )
                    self.delete_messages_from_chat(key)
                else:
                    modify_file_response = self.chat(
                        message,
                        message_key=key,
                    )
            except Exception as e:  # Check for max tokens error
                if "max tokens" in str(e).lower():
                    logger.error(
                        f"Max tokens exceeded for {file_change_request.filename}"
                    )
                    raise MaxTokensExceeded(file_change_request.filename)
            try:
                logger.info(
                    f"generate_new_file with contents: {contents} and modify_file_response: {modify_file_response}"
                )
                new_file, errors = generate_new_file_from_patch(
                    modify_file_response,
                    contents,
                    chunk_offset=chunk_offset,
                    sweep_context=self.sweep_context,
                )

                new_file = format_contents(new_file, file_markdown)

                commit_message_match = re.search(
                    'Commit message: "(?P<commit_message>.*)"', modify_file_response
                )
                if commit_message_match:
                    commit_message = commit_message_match.group("commit_message")
                else:
                    commit_message = f"Updated {file_change_request.filename}"
                commit_message = commit_message[: min(len(commit_message), 50)]

                # self.delete_messages_from_chat(key)

                # proposed_diffs = get_all_diffs(modify_file_response)
                # proposed_diffs = (
                #     f"<proposed_diffs>\n{proposed_diffs}\n</proposed_diffs>\n\n"
                #     if proposed_diffs
                #     else ""
                # )

                # validation step
                # logger.info("Validating file change request...")
                # new_diffs = self.chat(
                #     code_repair_modify_prompt.format(
                #         filename=file_change_request.filename,
                #         instructions=file_change_request.instructions,
                #         code=new_file,
                #     ),
                #     message_key=key + "-validation",
                # )

                # final_file, errors = generate_new_file_from_patch(
                #     new_diffs,
                #     new_file,
                #     chunk_offset=chunk_offset,
                #     sweep_context=self.sweep_context,
                # )

                # final_file = format_contents(final_file, file_markdown)
                # logger.info("Done validating file change request")

                # return final_file, commit_message
                return new_file, commit_message
            except Exception as e:
                tb = traceback.format_exc()
                logger.warning(
                    f"Failed to parse. Retrying for the {count}th time. Received error {e}\n{tb}"
                )
                self.delete_messages_from_chat(key)
                continue
        raise Exception(f"Failed to parse response after {retries} attempts.")

    def change_files_in_github(
        self,
        file_change_requests: list[ProposedIssue],
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
        file_change_requests: list[ProposedIssue],
        branch: str,
        blocked_dirs: list[str],
        sandbox=None,
    ):
        # should check if branch exists, if not, create it
        logger.debug(file_change_requests)
        num_fcr = len(file_change_requests)
        completed = 0

        added_modify_hallucination = False

        for file_change_request in file_change_requests:
            changed_file = False
            try:
                if self.is_blocked(file_change_request.filename, blocked_dirs)[
                    "success"
                ]:
                    logger.info(
                        f"Skipping {file_change_request.filename} because it is blocked."
                    )
                    continue

                print(
                    f"Processing {file_change_request.filename} for change type {file_change_request.change_type}..."
                )
                match file_change_request.change_type:
                    case "create":
                        changed_file = self.handle_create_file(
                            file_change_request, branch, sandbox=sandbox
                        )
                    case "modify":
                        # Add example for more consistent generation
                        if not added_modify_hallucination:
                            added_modify_hallucination = True
                            # Add hallucinated example for better parsing
                            for message in modify_file_hallucination_prompt:
                                self.messages.append(Message(**message))

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

                        changed_file = self.handle_modify_file(
                            file_change_request, branch, sandbox=sandbox
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
                            f"Renamed {file_change_request.filename} to {file_change_request.instructions}",
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
                print(f"Done processing {file_change_request.filename}.")
                yield file_change_request, changed_file
            except MaxTokensExceeded as e:
                raise e
            except Exception as e:
                logger.error(f"Error in change_files_in_github {e}")

            if changed_file:
                completed += 1
        return completed, num_fcr

    def handle_create_file(
        self, file_change_request: ProposedIssue, branch: str, sandbox=None
    ):
        try:
            file_change = self.create_file(file_change_request)
            file_markdown = is_markdown(file_change_request.filename)
            file_change.code = format_contents(file_change.code, file_markdown)
            logger.debug(
                f"{file_change_request.filename}, {f'Create {file_change_request.filename}'}, {file_change.code}, {branch}"
            )

            if sandbox is not None:
                try:
                    # Format file
                    loop = asyncio.get_event_loop()
                    # run for up to 10 seconds
                    file_change.code = loop.run_until_complete(
                        asyncio.wait_for(
                            sandbox.run_formatter(
                                file_change_request.filename, file_change.code
                            ),
                            timeout=30,
                        )
                    )

                    # Run linter on file
                    lint_results = loop.run_until_complete(
                        asyncio.wait_for(
                            sandbox.run_linter(
                                file_change_request.filename, file_change.code
                            ),
                            timeout=30,
                        )
                    )

                    if lint_results:
                        # Todo: pass this file to review in sweep_bot
                        pass

                except Exception as e:
                    # print e and print traceback
                    print(e)
                    print("\n\n")
                    print(traceback.format_exc())
                    print("OOPS E2B modify")

            self.repo.create_file(
                file_change_request.filename,
                file_change.commit_message,
                file_change.code,
                branch=branch,
            )

            file_change_request.new_content = file_change.code

            return True
        except Exception as e:
            logger.info(f"Error in handle_create_file: {e}")
            return False

    def handle_modify_file(
        self,
        file_change_request: ProposedIssue,
        branch: str,
        commit_message: str = None,
        sandbox=None,
    ):
        CHUNK_SIZE = 800  # Number of lines to process at a time
        try:
            file = self.get_file(file_change_request.filename, branch=branch)
            file_contents = file.decoded_content.decode("utf-8")
            lines = file_contents.split("\n")

            new_file_contents = (
                ""  # Initialize an empty string to hold the new file contents
            )
            all_lines_numbered = [f"{i + 1}:{line}" for i, line in enumerate(lines)]
            chunk_sizes = [
                800,
                600,
                400,
            ]  # Define the chunk sizes for the backoff mechanism
            for CHUNK_SIZE in chunk_sizes:
                try:
                    chunking = (
                        len(lines) > CHUNK_SIZE * 1.5
                    )  # Only chunk if the file is large enough
                    file_name = file_change_request.filename
                    if not chunking:
                        new_file_contents, suggested_commit_message = self.modify_file(
                            file_change_request,
                            contents="\n".join(lines),
                            branch=branch,
                            contents_line_numbers=file_contents
                            if USING_DIFF
                            else "\n".join(all_lines_numbered),
                            chunking=chunking,
                            chunk_offset=0,
                        )
                        commit_message = suggested_commit_message
                        # commit_message = commit_message or suggested_commit_message
                    else:
                        for i in range(0, len(lines), CHUNK_SIZE):
                            chunk_contents = "\n".join(lines[i : i + CHUNK_SIZE])
                            contents_line_numbers = "\n".join(
                                all_lines_numbered[i : i + CHUNK_SIZE]
                            )
                            if not EditBot().should_edit(
                                issue=file_change_request.instructions,
                                snippet=chunk_contents,
                            ):
                                new_chunk = chunk_contents
                            else:
                                new_chunk, suggested_commit_message = self.modify_file(
                                    file_change_request,
                                    contents=chunk_contents,
                                    branch=branch,
                                    contents_line_numbers=file_contents
                                    if USING_DIFF
                                    else "\n".join(contents_line_numbers),
                                    chunking=chunking,
                                    chunk_offset=i,
                                )
                                # commit_message = commit_message or suggested_commit_message
                                commit_message = suggested_commit_message
                            if i + CHUNK_SIZE < len(lines):
                                new_file_contents += new_chunk + "\n"
                            else:
                                new_file_contents += new_chunk
                    break  # If the chunking was successful, break the loop
                except Exception:
                    continue  # If the chunking was not successful, continue to the next chunk size
            # If the original file content is identical to the new file content, log a warning and return
            if file_contents == new_file_contents:
                logger.warning(
                    f"No changes made to {file_change_request.filename}. Skipping file update."
                )
                return False
            logger.debug(
                f"{file_name}, {commit_message}, {new_file_contents}, {branch}"
            )

            # Format the contents
            if sandbox is not None:
                try:
                    # Todo(lukejagg): Work with E2B to get this working in Modal stub
                    loop = asyncio.get_event_loop()
                    new_file_contents = loop.run_until_complete(
                        asyncio.wait_for(
                            sandbox.run_formatter(file_name, new_file_contents),
                            timeout=30,
                        )
                    )

                    # Run linter on file
                    lint_results = loop.run_until_complete(
                        asyncio.wait_for(
                            sandbox.run_linter(
                                file_change_request.filename, file_change.code
                            ),
                            timeout=30,
                        )
                    )

                    if lint_results:
                        # Todo: pass this file to review in sweep_bot

                        pass
                except Exception as e:
                    # print e and print traceback
                    print(e)
                    print("\n\n")
                    print(traceback.format_exc())
                    print("OOPS E2B")

            # Update the file with the new contents after all chunks have been processed
            try:
                self.repo.update_file(
                    file_name,
                    # commit_message.format(file_name=file_name),
                    commit_message,
                    new_file_contents,
                    file.sha,
                    branch=branch,
                )
                file_change_request.new_content = new_file_contents
                return True
            except Exception as e:
                logger.info(f"Error in updating file, repulling and trying again {e}")
                file = self.get_file(file_change_request.filename, branch=branch)
                self.repo.update_file(
                    file_name,
                    # commit_message.format(file_name=file_name),
                    commit_message,
                    new_file_contents,
                    file.sha,
                    branch=branch,
                )
                file_change_request.new_content = new_file_contents
                return True
        except MaxTokensExceeded as e:
            raise e
        except Exception as e:
            tb = traceback.format_exc()
            logger.info(f"Error in handle_modify_file: {tb}")
            return False
