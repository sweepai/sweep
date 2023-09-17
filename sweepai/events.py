from typing import Any, Literal, Dict

from pydantic import BaseModel


class Account(BaseModel):
    id: int
    login: str
    type: str


class Installation(BaseModel):
    id: Any | None = None
    account: Account | None = None


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
            type: str

        body: str | None
        original_line: int
        path: str
        diff_hunk: str
        user: User
        id: int

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
            url: str | None

        title: str
        number: int
        html_url: str
        user: User
        body: str | None
        labels: list[Label]
        assignees: list[Assignee] | None = None
        pull_request: PullRequest | None = None

    action: str
    issue: Issue
    repository: Issue.Repository
    assignee: Issue.Assignee | None = None
    installation: Installation | None = None
    sender: Issue.User


class IssueCommentChanges(BaseModel):
    "changes/body/from"

    class Body(BaseModel):
        body: Dict[str, str]

    changes: Body


class IssueCommentRequest(IssueRequest):
    class Comment(BaseModel):
        class User(BaseModel):
            login: str
            type: Literal["User", "Bot"]

        user: User
        id: int
        body: str

    comment: Comment
    sender: Comment.User


class PRRequest(BaseModel):
    class PullRequest(BaseModel):
        class User(BaseModel):
            login: str

        title: str

        class MergedBy(BaseModel):
            login: str

        user: User
        merged_by: MergedBy | None
        additions: int = 0
        deletions: int = 0

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
