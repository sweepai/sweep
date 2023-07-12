from typing import Literal

from pydantic import BaseModel


class Installation(BaseModel):
    id: str


class InstallationCreatedRequest(BaseModel):
    class Repository(BaseModel):
        full_name: str

    repositories: list[Repository]
    installation: Installation


class ReposAddedRequest(BaseModel):
    class Repository(BaseModel):
        full_name: str

    repositories_added: list[Repository]
    installation: Installation


class CommentCreatedRequest(BaseModel):
    class Comment(BaseModel):
        class User(BaseModel):
            login: str

        body: str | None
        original_line: int
        path: str
        diff_hunk: str
        user: User

    class PullRequest(BaseModel):
        class Head(BaseModel):
            ref: str

        number: int
        body: str | None
        state: str  # "closed" or "open"
        head: Head
        title: str

    class Repository(BaseModel):
        full_name: str
        description: str | None

    class Sender(BaseModel):
        pass

    action: str
    comment: Comment
    pull_request: PullRequest
    repository: Repository
    sender: Sender
    installation: Installation


class IssueRequest(BaseModel):
    class Issue(BaseModel):
        class User(BaseModel):
            login: str
            type: str

        class Assignee(BaseModel):
            login: str

        class Repository(BaseModel):
            # TODO(sweep): Move this out
            full_name: str
            description: str | None

        class Label(BaseModel):
            name: str

        class PullRequest(BaseModel):
            pass

        pull_request: PullRequest | None
        title: str
        number: int
        html_url: str
        user: User
        body: str | None
        labels: list[Label]
        assignees: list[Assignee]

    action: str
    issue: Issue
    repository: Issue.Repository
    assignee: Issue.Assignee | None
    installation: Installation


class IssueCommentRequest(IssueRequest):
    class Comment(BaseModel):
        class User(BaseModel):
            login: str
            type: Literal["User", "Bot"]

        user: User
        id: int
        body: str

    comment: Comment


class PRRequest(BaseModel):
    class PullRequest(BaseModel):
        class User(BaseModel):
            login: str

        class MergedBy(BaseModel):
            login: str

        user: User
        merged_by: MergedBy

    class Repository(BaseModel):
        full_name: str

    pull_request: PullRequest
    repository: Repository


class CheckRunCompleted(BaseModel):
    class CheckRun(BaseModel):
        class PullRequest(BaseModel):
            number: int

        conclusion: str
        html_url: str
        pull_requests: list[PullRequest]

        @property
        def run_id(self):
            # format is like https://github.com/ORG/REPO_NAME/actions/runs/RUN_ID/jobs/JOB_ID
            return self.html_url.split("/")[-3]

    class Repository(BaseModel):
        full_name: str
        description: str | None

    class Sender(BaseModel):
        login: str

    check_run: CheckRun
    installation: Installation
    repository: Repository
    sender: Sender
