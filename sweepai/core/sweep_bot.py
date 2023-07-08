from __future__ import annotations

from functools import cached_property
from loguru import logger
from github.Repository import Repository
from github.ContentFile import ContentFile
from github.GithubException import GithubException
import modal
from pydantic import BaseModel
from sweepai.core.code_repair import CodeRepairer
from sweepai.utils.chat_logger import ChatLogger

from sweepai.core.entities import (
    FileChange,
    FileChangeRequest,
    FilesToChange,
    PullRequest,
    RegexMatchError,
    Function,
    Snippet
)
from sweepai.core.chat import ChatGPT
from sweepai.core.prompts import (
    files_to_change_prompt,
    pull_request_prompt,
    create_file_prompt,
    modify_file_prompt,
    modify_file_plan_prompt,
)
from sweepai.utils.config import SweepConfig
from sweepai.utils.constants import DB_NAME
from sweepai.utils.diff import format_contents, generate_diff, generate_new_file, is_markdown, revert_whitespace_changes


class CodeGenBot(ChatGPT):

    def get_files_to_change(self):
        file_change_requests: list[FileChangeRequest] = []
        for count in range(5):
            try:
                logger.info(f"Generating for the {count}th time...")
                files_to_change_response = self.chat(files_to_change_prompt, message_key="files_to_change") # Dedup files to change here
                files_to_change = FilesToChange.from_string(files_to_change_response)
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
                        file_instructions_dict[file_change_request.filename] = (instructions + " " + file_change_request.instructions, change_type)
                    else:
                        file_instructions_dict[file_change_request.filename] = (file_change_request.instructions, file_change_request.change_type)
                file_change_requests = [FileChangeRequest(filename=file_name, instructions=instructions, change_type=change_type) for file_name, (instructions, change_type) in file_instructions_dict.items()]
                if file_change_requests:
                    return file_change_requests
            except RegexMatchError:
                logger.warning("Failed to parse! Retrying...")
                self.delete_messages_from_chat("files_to_change")
                continue
        raise Exception("Could not generate files to change")

    def generate_pull_request(self) -> PullRequest:
        pull_request = None
        for count in range(5):
            try:
                logger.info(f"Generating for the {count}th time...")
                pr_text_response = self.chat(pull_request_prompt, message_key="pull_request")
            except Exception as e:
                logger.warning(f"Exception {e}. Failed to parse! Retrying...")
                self.undo()
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
            branch = self.base_branch
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

    def create_branch(self, branch: str) -> str:
        # Generate PR if nothing is supplied maybe
        base_branch = self.repo.get_branch(self.base_branch)
        try:
            self.repo.create_git_ref(f"refs/heads/{branch}", base_branch.commit.sha)
            return branch
        except GithubException as e:
            logger.error(f"Error: {e}, trying with other branch names...")
            for i in range(1, 100):
                try:
                    logger.warning(f"Retrying {branch}_{i}...")
                    self.repo.create_git_ref(
                        f"refs/heads/{branch}_{i}", base_branch.commit.sha
                    )
                    return f"{branch}_{i}"
                except GithubException:
                    pass
            raise e
    
    def populate_snippets(self, snippets: list[Snippet]):
        for snippet in snippets:
            try:
                snippet.content = self.repo.get_contents(snippet.file_path).decoded_content.decode("utf-8")
            except Exception as e:
                logger.error(snippet)
    
    def search_snippets(
        self, 
        query: str, 
        installation_id: str,
        num_snippets: int = 30,
    ) -> list[Snippet]:
        get_relevant_snippets = modal.Function.lookup(DB_NAME, "get_relevant_snippets")
        snippets: list[Snippet] = get_relevant_snippets.call(
            self.repo.full_name, 
            query=query,
            n_results=num_snippets,
            installation_id=installation_id,
        )
        self.populate_snippets(snippets)
        return snippets
    
    def validate_file_change_requests(self, file_change_requests: list[FileChangeRequest]):
        for file_change_request in file_change_requests:
            try:
                contents = self.repo.get_contents(file_change_request.filename)
                if contents:
                    file_change_request.change_type = "modify"
                else:
                    file_change_request.change_type = "create"
            except:
                file_change_request.change_type = "create"
        return file_change_requests

class SweepBot(CodeGenBot, GithubBot):
    config: SweepConfig

    @property
    def base_branch(self) -> str:
        print(self.config.sweep_branch)
        return self.config.sweep_branch or self.repo.default_branch

    @classmethod
    def from_system_message_content(
        cls, 
        repo: Repository,
        **kwargs
    ) -> SweepBot:
        return cls(
            config=SweepConfig.from_repo(repo),
            repo=repo,
            **kwargs
        )

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
                } # manage file too large
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
        return

    def create_file(self, file_change_request: FileChangeRequest) -> FileChange:
        file_change: FileChange | None = None
        for count in range(5):
            create_file_response = self.chat(
                create_file_prompt.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                ),
                message_key=f"file_change_{file_change_request.filename}",
            )
            # Add file to list of changed_files
            self.file_change_paths.append(file_change_request.filename)
            # self.delete_file_from_system_message(file_path=file_change_request.filename)
            try:
                file_change = FileChange.from_string(create_file_response)
                assert file_change is not None
                file_change.commit_message = f"sweep: {file_change.commit_message[:50]}"
                return file_change
            except Exception:
                logger.warning(f"Failed to parse. Retrying for the {count}th time...")
                self.undo()
                continue
        raise Exception("Failed to parse response after 5 attempts.")

    def modify_file(
        self, file_change_request: FileChangeRequest, contents: str = ""
    ) -> tuple[str, str]:
        if not contents:
            contents = self.get_file(
                file_change_request.filename
            ).decoded_content.decode("utf-8")
        # Add line numbers to the contents; goes in prompts but not github
        contents_line_numbers = "\n".join([f"{i + 1}:{line}" for i, line in enumerate(contents.split("\n"))])
        contents_line_numbers = contents_line_numbers.replace('"""', "'''")
        for count in range(5):
            if "0613" in self.model:
                _ = self.chat( # We don't use the plan in the next call
                    modify_file_plan_prompt.format(
                        filename=file_change_request.filename,
                        instructions=file_change_request.instructions,
                        code=contents_line_numbers,
                    ),
                    message_key=f"file_change_{file_change_request.filename}",
                )
                modify_file_response = self.chat(
                    modify_file_prompt,
                    message_key=f"file_change_{file_change_request.filename}",
                )
                try:
                    logger.info(f"modify_file_response: {modify_file_response}")
                    new_file = generate_new_file(modify_file_response, contents)
                    if not is_markdown(file_change_request.filename):
                        code_repairer = CodeRepairer(chat_logger=self.chat_logger)
                        diff = generate_diff(old_code=contents, new_code=new_file)
                        new_file = code_repairer.repair_code(diff=diff, user_code=new_file, feature=file_change_request.instructions)
                        # new_file = revert_whitespace_changes(original_file_str=contents, modified_file_str=new_file)
                    return (new_file, file_change_request.filename)
                except Exception as e:
                    logger.warning(f"Recieved error {e}")
                    logger.warning(
                        f"Failed to parse. Retrying for the {count}th time..."
                    )
                    self.undo()
                    self.undo()
                    continue
        raise Exception("Failed to parse response after 5 attempts.")
 
    def change_file(self, file_change_request: FileChangeRequest):
        if file_change_request.change_type == "create":
            return self.create_file(file_change_request)
        elif file_change_request.change_type == "modify":
            return self.create_file(file_change_request)
        else:
            raise Exception("Not a valid file type")
        
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
                file_markdown = is_markdown(file_change_request.filename)
                if file_change_request.change_type == "create":
                    self.handle_create_file(file_change_request, branch, file_markdown)
                elif file_change_request.change_type == "modify":
                    self.handle_modify_file(file_change_request, branch, file_markdown)
            except Exception as e:
                logger.error(f"Error in change_files_in_github {e}")
            completed += 1
        return completed, num_fcr

    def handle_create_file(self, file_change_request: FileChangeRequest, branch: str, file_markdown: bool):
        try:
            file_change = self.create_file(file_change_request)
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

    def handle_modify_file(self, file_change_request: FileChangeRequest, branch: str, file_markdown: bool):
        try:
            contents = self.get_file(file_change_request.filename, branch=branch)
            new_file_contents, file_name = self.modify_file(
                file_change_request, contents.decoded_content.decode("utf-8")
            )
            new_file_contents = format_contents(new_file_contents, file_markdown)
            new_file_contents = new_file_contents.rstrip()
            logger.debug(
                f"{file_name}, {f'Update {file_name}'}, {new_file_contents}, {branch}"
            )
            self.repo.update_file(
                file_name,
                f'Update {file_name}',
                new_file_contents,
                contents.sha,
                branch=branch,
            )
        except Exception as e:
            logger.info(f"Error in handle_modify_file: {e}")
