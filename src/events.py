from pydantic import BaseModel


class Installation(BaseModel):
    id: str


class CommentCreatedRequest(BaseModel):
    class Comment(BaseModel):
        body: str
        position: int
        path: str

    class PullRequest(BaseModel):
        class Head(BaseModel):
            ref: str

        body: str
        state: str  # "closed" or "open"
        head: Head

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


class IssueRequest(BaseModel):
    class Issue(BaseModel):
        class User(BaseModel):
            login: str

        class Assignee(BaseModel):
            login: str

        class Repository(BaseModel):
            full_name: str
            description: str | None

        title: str
        number: int
        html_url: str
        user: User
        body: str | None
        labels: list[str]
        assignees: list[Assignee]

    action: str
    issue: Issue
    repository: Issue.Repository
    assignee: Issue.Assignee | None
    installation: Installation
