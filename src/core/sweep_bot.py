from loguru import logger
from github.Repository import Repository
from github.ContentFile import ContentFile
from github.GithubException import GithubException
from pydantic import BaseModel


from src.core.models import (
    ChatGPT,
    FileChange,
    FileChangeRequest,
    FilesToChange,
    PullRequest,
    RegexMatchError,
)
from src.core.prompts import (
    files_to_change_prompt,
    pull_request_prompt,
    create_file_prompt,
    modify_file_prompt,
)


class CodeGenBot(ChatGPT):
    def get_files_to_change(self):
        file_change_requests: list[FileChangeRequest] = []
        for count in range(5):
            try:
                logger.info(f"Generating for the {count}th time...")
                files_to_change_response = self.chat(files_to_change_prompt)
                files_to_change = FilesToChange.from_string(files_to_change_response)
                files_to_create: list[str] = files_to_change.files_to_create.split("*")
                files_to_modify: list[str] = files_to_change.files_to_modify.split("*")
                logger.debug(files_to_change)
                for file_change_request, change_type in zip(
                    files_to_create + files_to_modify,
                    ["create"] * len(files_to_create)
                    + ["modify"] * len(files_to_modify),
                ):
                    file_change_request = file_change_request.strip()
                    if not file_change_request or file_change_request == "None":
                        continue
                    logger.debug(file_change_request, change_type)
                    file_change_requests.append(
                        FileChangeRequest.from_string(
                            file_change_request, change_type=change_type
                        )
                    )
                if file_change_requests:
                    return file_change_requests
            except RegexMatchError:
                logger.warning("Failed to parse! Retrying...")
                self.undo()
                continue
        raise Exception("Could not generate files to change")

    def generate_pull_request(self):
        pull_request = None
        for count in range(5):
            try:
                logger.info(f"Generating for the {count}th time...")
                pr_text_response = self.chat(pull_request_prompt)
                pull_request = PullRequest.from_string(pr_text_response)
                pull_request.branch_name = "sweep/" + pull_request.branch_name[:250]
                return pull_request
            except Exception:
                logger.warning("Failed to parse! Retrying...")
                self.undo()
                continue
        raise Exception("Could not generate PR text")


class GithubBot(BaseModel):
    class Config:
        arbitrary_types_allowed = True  # for repo: Repository

    repo: Repository

    def get_contents(self, path: str, branch: str = ""):
        if not branch:
            branch = self.repo.default_branch
        return self.repo.get_contents(path, ref=branch)

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
        base_branch = self.repo.get_branch(self.repo.default_branch)
        try:
            self.repo.create_git_ref(f"refs/heads/{branch}", base_branch.commit.sha)
            return branch
        except GithubException as e:
            logger.error(f"Error: {e}")
            for i in range(1, 10):
                try:
                    self.repo.create_git_ref(
                        f"refs/heads/{branch}_{i}", base_branch.commit.sha
                    )
                    return f"{branch}_{i}"
                except GithubException:
                    pass
            raise e


class SweepBot(CodeGenBot, GithubBot):
    def create_file(self, file_change_request: FileChangeRequest) -> FileChange:
        file_change: FileChange | None = None
        for count in range(5):
            create_file_response = self.chat(
                create_file_prompt.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                )
            )
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
    ) -> FileChange:
        if not contents:
            contents = self.get_file(
                file_change_request.filename
            ).decoded_content.decode("utf-8")
        file_change: FileChange | None = None
        for count in range(5):
            modify_file_response = self.chat(
                modify_file_prompt.format(
                    filename=file_change_request.filename,
                    instructions=file_change_request.instructions,
                    code=contents,
                )
            )
            try:
                file_change = FileChange.from_string(modify_file_response)
                assert file_change is not None
                file_change.commit_message = f"sweep: {file_change.commit_message[:50]}"
                return file_change
            except Exception:
                logger.warning(
                    f"Failed to parse. Retryinging for the {count}th time..."
                )
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
        for file_change_request in file_change_requests:
            if file_change_request.change_type == "create":
                file_change = self.create_file(file_change_request)
                logger.debug(
                    f"{file_change_request.filename}, {file_change.commit_message}, {file_change.code}, {branch}"
                )
                self.repo.create_file(
                    file_change_request.filename,
                    file_change.commit_message,
                    file_change.code,
                    branch=branch,
                )
            elif file_change_request.change_type == "modify":
                contents = self.get_file(file_change_request.filename, branch=branch)
                file_change = self.modify_file(
                    file_change_request, contents.decoded_content.decode("utf-8")
                )
                logger.debug(
                    f"{file_change_request.filename}, {file_change.commit_message}, {file_change.code}, {branch}"
                )
                self.repo.update_file(
                    file_change_request.filename,
                    file_change.commit_message,
                    file_change.code,
                    contents.sha,
                    branch=branch,
                )
            else:
                raise Exception("Invalid change type")
