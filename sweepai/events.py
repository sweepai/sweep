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


class ReviewSubmittedRequest(BaseModel):
    class User(BaseModel):
        login: str
        id: int
        node_id: str
        avatar_url: str
        gravatar_id: str
        url: str
        html_url: str
        followers_url: str
        following_url: str
        gists_url: str
        starred_url: str
        subscriptions_url: str
        organizations_url: str
        repos_url: str
        events_url: str
        received_events_url: str
        type: str
        site_admin: bool

    class Links(BaseModel):
        class Html(BaseModel):
            href: str

        class PullRequest(BaseModel):
            href: str

        html: Html
        pull_request: PullRequest

    class Review(BaseModel):
        id: int
        node_id: str
        user: User
        body: str
        commit_id: str
        submitted_at: str
        state: str
        html_url: str
        pull_request_url: str
        author_association: str
        _links: Links

    class PullRequest(BaseModel):
        url: str
        id: int
        node_id: str
        html_url: str
        diff_url: str
        patch_url: str
        issue_url: str
        number: int
        state: str
        locked: bool
        title: str
        user: User
        body: str
        created_at: str
        updated_at: str
        closed_at: str | None
        merged_at: str | None
        merge_commit_sha: str
        assignee: str | None
        assignees: list[str]

    action: str
    review: Review
    pull_request: PullRequest
