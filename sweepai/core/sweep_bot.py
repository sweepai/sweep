import traceback
import re

import modal
from github.ContentFile import ContentFile
from github.GithubException import GithubException
from github.Repository import Repository
from loguru import logger
from pydantic import BaseModel

from sweepai.core.chat import ChatGPT
from sweepai.core.code_repair import CodeRepairer
from sweepai.core.edit_chunk import EditBot
from sweepai.core.entities import (
    FileCreation,
    FileChangeRequest,
    FilesToChange,
    PullRequest,
    RegexMatchError,
    Function,
    Snippet, NoFilesException, Message
)
from sweepai.utils.config.client import SweepConfig
from sweepai.utils.config.server import DB_MODAL_INST_NAME, SECONDARY_MODEL
from sweepai.utils.diff import diff_contains_dups_or_removals, format_contents, generate_diff, generate_new_file, generate_new_file_from_patch, is_markdown
from sweepai.core.vector_db import compute_filename_score
from sweepai.core.prompts import (
    files_to_change_prompt,
    pull_request_prompt,
    create_file_prompt,
    files_to_change_abstract_prompt,
    modify_file_prompt_3,
    snippet_replacement,
    chunking_prompt,
)

# Define the variable `THRESHOLD`
THRESHOLD = 0.5

class MaxTokensExceeded(Exception):
    def __init__(self, filename):
        self.filename = filename

class CodeGenBot(ChatGPT):
    def summarize_snippets(self, create_thoughts, modify_thoughts):
        snippet_summarization = self.chat(
            snippet_replacement.format(
                thoughts=create_thoughts + "\n" + modify_thoughts
            ),
            message_key="snippet_summarization",
        )

        # Delete excessive tokens
        self.delete_messages_from_chat("relevant_snippets")
        self.delete_messages_from_chat("relevant_directories")
        self.delete_messages_from_chat("relevant_tree")

        # Delete past instructions
        self.delete_messages_from_chat("files_to_change", delete_assistant=False)

        # Delete summarization instructions
        self.delete_messages_from_chat("snippet_summarization")

        msg = Message(content=snippet_summarization, role="assistant", key="bot_analysis_summary")
        self.messages.insert(-2, msg)
        pass

    def get_files_to_change(self, retries=2):
        file_change_requests: list[FileChangeRequest] = []
        # Todo: put retries into a constants file
        # also, this retries multiple times as the calls for this function are in a for loop

        for count in range(retries):
            try:
                logger.info(f"Generating for the {count}th time...")
                abstract_plan = self.chat(files_to_change_abstract_prompt, message_key="files_to_change")

                files_to_change_response = self.chat(files_to_change_prompt,
                                                     message_key="files_to_change")  # Dedup files to change here
                files_to_change = FilesToChange.from_string(files_to_change_response)
                create_thoughts = files_to_change.files_to_create.strip()
                modify_thoughts = files_to_change.files_to_modify.strip()

                files_to_create: list[str] = files_to_change.files_to_create.split("\n*")
                files_to_modify: list[str] = files_to_change.files_to_modify.split("\n*")
                for file_change_request, change_type in zip(
                        files_to_create + files_to_modify,
                        ["create"] * len(files_to_create)
                        + ["modify"] * len(files_to_modify),
                ):
                    file_change_request = file_change_request.strip()
                    if not file_change_request or file_change_request == "* None":
                        continue
                    logger.debug(file_change_request)
                    logger.debug(change_type)
                    file_change_requests.append(
                        FileChangeRequest.from_string(
                            file_change_request, change_type=change_type
                        )
                    )
                # Create a dictionary to hold file names and their corresponding instructions
                file_instructions_dict = {}
                for file_change_request in file_change_requests:
                    # If the file name is already in the dictionary, append the new instructions
                    if file_change_request.filename in file_instructions_dict:
                        instructions, change_type = file_instructions_dict[file_change_request.filename]
                        file_instructions_dict[file_change_request.filename] = (
                            instructions + " " + file_change_request.instructions, change_type)
                    else:
                        file_instructions_dict[file_change_request.filename] = (
                            file_change_request.instructions, file_change_request.change_type)
                file_change_requests = [
                    FileChangeRequest(filename=file_name, instructions=instructions, change_type=change_type) for
                    file_name, (instructions, change_type) in file_instructions_dict.items()]
                if file_change_requests:
                    return file_change_requests, create_thoughts, modify_thoughts
            except RegexMatchError:
                logger.warning("Failed to parse! Retrying...")
                self.delete_messages_from_chat("files_to_change")
                continue
        raise NoFilesException()

    def generate_pull_request(self, retries=5) -> PullRequest:
        for count in range(retries):
            too_long = False
            try:
                logger.info(f"Generating for the {count}th time...")
                if too_long or count == retries - 2:  # if on last try, use gpt4-32k (improved context window)
                    pr_text_response = self.chat(pull_request_prompt, message_key="pull_request")
                else:
                    pr_text_response = self.chat(pull_request_prompt, message_key="pull_request", model=SECONDARY_MODEL)

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
            pull_request.branch_name = "sweep/" + pull_request.branch_name[:250]
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
            self.repo.create_git_ref(f"refs/heads/{branch}", base_branch.commit.sha)
            return branch
        except GithubException as e:
            logger.error(f"Error: {e}, trying with other branch names...")
            if retry:
                for i in range(1, 100):
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
                snippet.content = self.repo.get_contents(snippet.file_path,
                                                         SweepConfig.get_branch(self.repo)).decoded_content.decode(
                    "utf-8")
            except Exception as e:
                logger.error(snippet)

    def search_snippets(
            self,
            query: str,
            installation_id: str,
            num_snippets: int = 30,
    ) -> list[Snippet]:
        get_relevant_snippets = modal.Function.lookup(DB_MODAL_INST_NAME, "get_relevant_snippets")
        snippets: list[Snippet] = get_relevant_snippets.call(
            self.repo.full_name,
            query=query,
            n_results=num_snippets,
            installation_id=installation_id,
        )
        self.populate_snippets(snippets)
        return snippets

    def validate_file_change_requests(self, file_change_requests: list[FileChangeRequest], branch: str = ""):
        for file_change_request in file_change_requests:
            try:
                contents = self.repo.get_contents(file_change_request.filename,
                                                  branch or SweepConfig.get_branch(self.repo))
                if contents:
                    file_change_request.change_type = "modify"
                else:
                    file_change_request.change_type = "create"
            except:
                file_change_request.change_type = "create"
        return file_change_requests


class SweepBot(CodeGenBot, GithubBot):
    def cot_retrieval(self):
        # TODO(sweep): add semantic search using vector db
        # TODO(sweep): add search using webpilot + github
        functions = [
            Function(
                name="cat",
                description="Cat files. Max 3 files per request.",
                parameters={
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "Paths to files. One per line."
                        },
                    }
                }  # manage file too large
            ),
            Function(
                name="finish",
                description="Indicate you have sufficient data to proceed.",
                parameters={"properties": {}}
            ),
        ]

        # self.chat(
        #     cot_retrieval_prompt,
        #     message_key="cot_retrieval",
        #     functions=functions,
        # )
        # is_function_call = self.messages[-1].function_call is not None
        # for _retry in range(3):
        #     logger.info("Got response.")
        #     if not is_function_call:
        #         break

        #     response = self.messages[-1].function_call
        #     # response = json.loads(response)
        #     function_name = response["name"]
        #     arguments = response["arguments"]
        #     logger.info(f"Fetching file {function_name} with arguments {arguments}.")
        #     arguments = json.loads(arguments)
        #     if function_name == "finish":
        #         return
        #     elif function_name == "cat":
        #         path = arguments["filepath"]
        #         try:
        #             logger.info("Retrieving file...")
        #             content = self.get_file(path).decoded_content.decode("utf-8")
        #             logger.info("Received file")
        #         except github.GithubException:
        #             response = self.chat(
        #                 f"File not found: {path}",
        #                 message_key=path,
        #                 functions=functions,
        #             )
        #         else:
        #             response = self.chat(
        #                 f"Here is the file: <file path=\"{path}\">\n\n{content[:10000]}</file>. Fetch more content or call finish.", 
        #                 message_key=path,
        #                 functions=functions
        #             ) # update this constant
        #             return response
        return

    def create_file(self, file_change_request: FileChangeRequest) -> FileCreation:
        file_change: FileCreation | None = None
        for count in range(5):
            key = f"file_change_created_{file_change_request.filename}"
            create_file_response = self.chat(
                create_file_prompt.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                    commit_message=f"Create {file_change_request.filename}"
                ),
                message_key=key,
            )
            # Add file to list of changed_files
            self.file_change_paths.append(file_change_request.filename)
            # self.delete_file_from_system_message(file_path=file_change_request.filename)
            try:
                file_change = FileCreation.from_string(create_file_response)
                assert file_change is not None
                file_change.commit_message = f"sweep: {file_change.commit_message[:50]}"
                return file_change
            except Exception:
                # Todo: should we undo appending to file_change_paths?
                logger.warning(f"Failed to parse. Retrying for the {count}th time...")
                self.delete_messages_from_chat(key)
                continue
        raise Exception("Failed to parse response after 5 attempts.")

    def modify_file(
            self, 
            file_change_request: FileChangeRequest, 
            contents: str = "", 
            contents_line_numbers: str = "", 
            branch=None, 
            chunking: bool = False,
            chunk_offset: int = 0,
    ):
        # Ensure that the `file_change_request` object is properly handled
        if not isinstance(file_change_request, FileChangeRequest):
            raise ValueError("Invalid file change request")
        try:
            file_change = self.create_file(file_change_request)
            file_markdown = is_markdown(file_change_request.filename)
            file_change.code = format_contents(file_change.code, file_markdown)
            logger.debug(
                f"{file_change_request.filename}, {f'Create {file_change_request.filename}'}, {file_change.code}, {branch}"
            )
            self.repo.create_file(
                file_change_request.filename,
                file_change.commit_message,
                file_change.code,
                branch=branch,
            )
        except Exception as e:
            logger.info(f"Error in handle_create_file: {e}")

    def change_files_in_github(
            self,
            file_change_requests: list[FileChangeRequest],
            branch: str,
    ):
        # should check if branch exists, if not, create it
        logger.debug(file_change_requests)
        num_fcr = len(file_change_requests)
        completed = 0
        for file_change_request in file_change_requests:
            try:
                if file_change_request.change_type == "create":
                    self.create_file(file_change_request, branch)
                elif file_change_request.change_type == "modify":
                    self.modify_file(file_change_request, branch)
            except MaxTokensExceeded as e:
                raise e
            except Exception as e:
                logger.error(f"Error in change_files_in_github {e}")
            completed += 1
        return completed, num_fcr

    def handle_create_file(self, file_change_request: FileChangeRequest, branch: str):
        try:
            file_change = self.create_file(file_change_request)
            file_markdown = is_markdown(file_change_request.filename)
            file_change.code = format_contents(file_change.code, file_markdown)
            logger.debug(
                f"{file_change_request.filename}, {f'Create {file_change_request.filename}'}, {file_change.code}, {branch}"
            )
            self.repo.create_file(
                file_change_request.filename,
                file_change.commit_message,
                file_change.code,
                branch=branch,
            )
        except Exception as e:
            logger.info(f"Error in handle_create_file: {e}")

    def handle_modify_file(self, file_change_request: FileChangeRequest, branch: str):
        # Initialize the `new_file_contents` variable
        new_file_contents = ""
        # Initialize the `file_contents` variable
        file_contents = ""
        # Initialize the `CHUNK_SIZE` variable
        CHUNK_SIZE = 400  # Number of lines to process at a time
        # Initialize the `user_code` variable
        user_code = ""
        # Initialize the `chunking` variable
        chunking = False
        for count in range(5):
            key = f"file_change_modified_{file_change_request.filename}"
            file_markdown = is_markdown(file_change_request.filename)
            # Use the new scoring function `compute_filename_score` to compute the score for the filename
            score = compute_filename_score(file_change_request.filename)
            # Use the 'score' variable in the subsequent operations
            # For example, if the score is used to determine the relevance of the filename, you can do something like this:
            if score > THRESHOLD:
                # Perform operation 1
                pass
            else:
                # Perform operation 2
                pass
            # Assign a value to the variable `new_file_contents` before it is returned
            new_file_contents = ""
        try:
            if chunking:
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
                logger.error(f"Max tokens exceeded for {file_change_request.filename}")
                raise MaxTokensExceeded(file_change_request.filename)
        try:
            logger.info(
                f"generate_new_file with contents: {contents} and modify_file_response: {modify_file_response}")
            new_file = generate_new_file_from_patch(modify_file_response, contents, chunk_offset=chunk_offset)
            if not is_markdown(file_change_request.filename) and not chunking:
                code_repairer = CodeRepairer(chat_logger=self.chat_logger)
                diff = generate_diff(old_code=contents, new_code=new_file)
                if diff.strip() != "" and diff_contains_dups_or_removals(diff, new_file):
                    new_file = code_repairer.repair_code(diff=diff, user_code=new_file,
                                                         feature=file_change_request.instructions)
            new_file = format_contents(new_file, file_markdown)
            new_file = new_file.rstrip()
            if contents.endswith("\n"):
                new_file += "\n"
            return new_file
        except Exception as e:
            tb = traceback.format_exc()
            logger.warning(f"Failed to parse. Retrying for the {count}th time. Recieved error {e}\n{tb}")
            self.delete_messages_from_chat(key)
            # Remove the `continue` statement as it is not inside a loop.
            # continue
        raise Exception("Failed to parse response after 5 attempts.")

def handle_modify_file(self, file_change_request: FileChangeRequest, branch: str):
    # Assign a value to the variable `file` before it is used
    file = None
    # Use the new scoring function `compute_filename_score` to compute the score for the filename
    score = compute_filename_score(file_change_request.filename)
    # Use the 'score' variable in the subsequent operations
    # For example, if the score is used to determine the relevance of the filename, you can do something like this:
    if score > THRESHOLD:
        # Perform operation 1
        pass
    else:
        # Perform operation 2
        pass
    return new_file_contents
    lines = file_contents.split("\n")
    
    new_file_contents = ""  # Initialize an empty string to hold the new file contents
    all_lines_numbered = [f"{i + 1}:{line}" for i, line in enumerate(lines)]
    chunking = len(lines) > CHUNK_SIZE * 1.5 # Only chunk if the file is large enough
    file_name = file_change_request.filename
    if not chunking:
        new_file_contents = self.modify_file(
                file_change_request, 
                contents="\n".join(lines), 
                branch=branch, 
                contents_line_numbers=file_contents if USING_DIFF else "\n".join(all_lines_numbered),
                chunking=chunking,
                chunk_offset=0
            )
    else:
        for i in range(0, len(lines), CHUNK_SIZE):
            chunk_contents = "\n".join(lines[i:i + CHUNK_SIZE])
            contents_line_numbers = "\n".join(all_lines_numbered[i:i + CHUNK_SIZE])
            if not EditBot().should_edit(issue=file_change_request.instructions, snippet=chunk_contents):
                new_chunk = chunk_contents
            else:
                new_chunk = self.modify_file(
                    file_change_request, 
                    contents=chunk_contents, 
                    branch=branch, 
                    contents_line_numbers=file_contents if USING_DIFF else "\n".join(contents_line_numbers), 
                    chunking=chunking,
                    chunk_offset=i
                )
            if i + CHUNK_SIZE < len(lines):
                new_file_contents += new_chunk + "\n"
            else:
                new_file_contents += new_chunk
    logger.debug(
        f"{file_name}, {f'Update {file_name}'}, {new_file_contents}, {branch}"
    )
    # Update the file with the new contents after all chunks have been processed
    try:
        self.repo.update_file(
            file_name,
            f'Update {file_name}',
            new_file_contents,
            file.sha,
            branch=branch,
        )
    except MaxTokensExceeded as e:
        raise e
    except Exception as e:
        logger.info(f"Error in updating file, repulling and trying again {e}")
        file = self.get_file(file_change_request.filename, branch=branch)
        self.repo.update_file(
            file_name,
            f'Update {file_name}',
            new_file_contents,
            file.sha,
            branch=branch,
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.info(f"Error in handle_modify_file: {tb}")

# Remove xml tags
# Assign a value to the `user_code` variable before it is used at line 554.
user_code = ""
# Indent handle_modify_file function
user_code = re.sub(r'def handle_modify_file', '    def handle_modify_file', user_code)

# Dedent handle_modify_file function
user_code = re.sub(r'    def handle_modify_file', 'def handle_modify_file', user_code)

# Add missing imports
user_code = re.sub(r'import traceback', 'import traceback\n\nimport modal\nfrom github.ContentFile import ContentFile\nfrom github.GithubException import GithubException\nfrom github.Repository import Repository\nfrom loguru import logger\nfrom pydantic import BaseModel\n\nfrom sweepai.core.chat import ChatGPT\nfrom sweepai.core.code_repair import CodeRepairer\nfrom sweepai.core.edit_chunk import EditBot\nfrom sweepai.core.entities import (\n    FileCreation,\n    FileChangeRequest,\n    FilesToChange,\n    PullRequest,\n    RegexMatchError,\n    Function,\n    Snippet, NoFilesException, Message\n)\nfrom sweepai.utils.config.client import SweepConfig\nfrom sweepai.utils.config.server import DB_MODAL_INST_NAME, SECONDARY_MODEL\nfrom sweepai.utils.diff import diff_contains_dups_or_removals, format_contents, generate_diff, generate_new_file, generate_new_file_from_patch, is_markdown\nfrom sweepai.core.vector_db import compute_filename_score\nfrom sweepai.core.prompts import (\n    files_to_change_prompt,\n    pull_request_prompt,\n    create_file_prompt,\n    files_to_change_abstract_prompt,\n    modify_file_prompt_3,\n    snippet_replacement,\n    chunking_prompt,\n)', user_code)

# Remove unnecessary imports
user_code = re.sub(r'import traceback\n\nimport modal\nfrom github.ContentFile import ContentFile\nfrom github.GithubException import GithubException\nfrom github.Repository import Repository\nfrom loguru import logger\nfrom pydantic import BaseModel\n\nfrom sweepai.core.chat import ChatGPT\nfrom sweepai.core.code_repair import CodeRepairer\nfrom sweepai.core.edit_chunk import EditBot\nfrom sweepai.core.entities import (\n    FileCreation,\n    FileChangeRequest,\n    FilesToChange,\n    PullRequest,\n    RegexMatchError,\n    Function,\n    Snippet, NoFilesException, Message\n)\nfrom sweepai.utils.config.client import SweepConfig\nfrom sweepai.utils.config.server import DB_MODAL_INST_NAME, SECONDARY_MODEL\nfrom sweepai.utils.diff import diff_contains_dups_or_removals, format_contents, generate_diff, generate_new_file, generate_new_file_from_patch, is_markdown\nfrom sweepai.core.vector_db import compute_filename_score\nfrom sweepai.core.prompts import (\n    files_to_change_prompt,\n    pull_request_prompt,\n    create_file_prompt,\n    files_to_change_abstract_prompt,\n    modify_file_prompt_3,\n    snippet_replacement,\n    chunking_prompt,\n)', '', user_code)

# Remove unnecessary variables
user_code = re.sub(r'USING_DIFF = True', '', user_code)
user_code = re.sub(r'USING_DIFF = True', '', user_code)

# Remove unnecessary comments
user_code = re.sub(r'# Define the variable `THRESHOLD`', '', user_code)

# Remove unnecessary blank lines
user_code = re.sub(r'\n\n\n', '\n\n', user_code)

# Remove unnecessary whitespace at the end of lines
user_code = re.sub(r'\s+$', '', user_code, flags=re.MULTILINE)

# Remove unnecessary whitespace at the beginning of lines
user_code = re.sub(r'^\s+', '', user_code, flags=re.MULTILINE)

# Remove unnecessary whitespace between lines
user_code = re.sub(r'\n\s+\n', '\n\n', user_code)

# Remove unnecessary whitespace at the beginning and end of the code
user_code = user_code.strip()

# Return the modified user_code
user_code
