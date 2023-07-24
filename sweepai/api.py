import time
import modal
from fastapi import HTTPException, Request
from loguru import logger
from pydantic import ValidationError
from sweepai.core.entities import PRChangeRequest

from sweepai.events import (
    CheckRunCompleted,
    CommentCreatedRequest,
    InstallationCreatedRequest,
    IssueCommentRequest,
    IssueRequest,
    PRRequest,
    ReposAddedRequest,
)
from sweepai.handlers.create_pr import create_pr  # type: ignore
from sweepai.handlers.on_check_suite import on_check_suite  # type: ignore
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_ticket import on_ticket
from sweepai.utils.config.server import DB_MODAL_INST_NAME, API_MODAL_INST_NAME, GITHUB_BOT_USERNAME, \
    GITHUB_LABEL_NAME, GITHUB_LABEL_COLOR, GITHUB_LABEL_DESCRIPTION, BOT_TOKEN_NAME
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client, index_full_repository

stub = modal.Stub(API_MODAL_INST_NAME)
stub.pr_queues = modal.Dict.new() # maps (repo_full_name, pull_request_ids) -> queues
image = (
    modal.Image.debian_slim()
    .apt_install("git", "universal-ctags")
    .run_commands(
        'export PATH="/usr/local/bin:$PATH"'
    )
    .pip_install(
        "openai",
        "anthropic",
        "PyGithub",
        "loguru",
        "docarray",
        "backoff",
        "tiktoken",
        "GitPython",
        "posthog",
        "tqdm",
        "pyyaml",
        "pymongo",
        "tabulate",
        "redis",
    )
)
secrets = [
    modal.Secret.from_name(BOT_TOKEN_NAME),
    modal.Secret.from_name("github"),
    modal.Secret.from_name("openai-secret"),
    modal.Secret.from_name("anthropic"),
    modal.Secret.from_name("posthog"),
    modal.Secret.from_name("mongodb"),
    modal.Secret.from_name("discord"),
    modal.Secret.from_name("redis_url"),
]

FUNCTION_SETTINGS = {
    "image": image,
    "secrets": secrets,
    "timeout": 30 * 60,
}

handle_ticket = stub.function(**FUNCTION_SETTINGS)(on_ticket)
handle_comment = stub.function(**FUNCTION_SETTINGS)(on_comment)
handle_pr = stub.function(**FUNCTION_SETTINGS)(create_pr)
update_index = modal.Function.lookup(DB_MODAL_INST_NAME, "update_index")
handle_check_suite = stub.function(**FUNCTION_SETTINGS)(on_check_suite)


@stub.function(**FUNCTION_SETTINGS)
def handle_pr_change_request(
    repo_full_name: str,
    pr_id: int
):
    # TODO: put process ID here and check if it's still running
    # TODO: GHA should have lower precedence than comments
    try:
        call_id, queue = stub.app.pr_queues[(repo_full_name, pr_id)]
        logger.info(f"Current queue: {queue}")
        while queue:
            # popping
            call_id, queue = stub.app.pr_queues[(repo_full_name, pr_id)]
            pr_change_request: PRChangeRequest
            *queue, pr_change_request = queue
            logger.info(f"Currently handling PR change request: {pr_change_request}")
            logger.info(f"PR queues: {queue}")

            if pr_change_request.type == "comment":
                handle_comment.call(**pr_change_request.params)
            elif pr_change_request.type == "gha":
                handle_check_suite.call(**pr_change_request.params)
            else:
                raise Exception(f"Unknown PR change request type: {pr_change_request.type}")
            stub.app.pr_queues[(repo_full_name, pr_id)] = (call_id, queue)
    finally:
        del stub.app.pr_queues[(repo_full_name, pr_id)]


def function_call_is_completed(call_id: str):
    if call_id == "0":
        return True

    from modal.functions import FunctionCall

    function_call = FunctionCall.from_id(call_id)
    try:
        function_call.get(timeout=0)
    except TimeoutError:
        return False

    return True

def push_to_queue(
    repo_full_name: str,
    pr_id: int,
    pr_change_request: PRChangeRequest
):
    key = (repo_full_name, pr_id)
    call_id, queue = stub.app.pr_queues[key] if key in stub.app.pr_queues else ("0", [])
    function_is_completed = function_call_is_completed(call_id)
    if pr_change_request.type == "comment" or function_is_completed:
        queue = [pr_change_request] + queue
        if function_is_completed:
            stub.app.pr_queues[key] = ("0", queue)
            call_id = handle_pr_change_request.spawn(
                repo_full_name=repo_full_name, 
                pr_id=pr_id
            ).object_id
        stub.app.pr_queues[key] = (call_id, queue)

@stub.function(**FUNCTION_SETTINGS)
@modal.web_endpoint(method="POST")
async def webhook(raw_request: Request):
    """Handle a webhook request from GitHub."""
    try:
        request_dict = await raw_request.json()
        logger.info(f"Received request: {request_dict.keys()}")
        event = raw_request.headers.get("X-GitHub-Event")
        assert event is not None
        action = request_dict.get("action", None)
        logger.info(f"Received event: {event}, {action}")
        match event, action:
            case "issues", "opened":
                request = IssueRequest(**request_dict)
                issue_title_lower = request.issue.title.lower()
                if issue_title_lower.startswith("sweep") or "sweep:" in issue_title_lower:
                    g = get_github_client(request.installation.id)
                    repo = g.get_repo(request.repository.full_name)

                    labels = repo.get_labels()
                    label_names = [label.name for label in labels]

                    if GITHUB_LABEL_NAME not in label_names:
                        repo.create_label(
                            name=GITHUB_LABEL_NAME,
                            color=GITHUB_LABEL_COLOR,
                            description=GITHUB_LABEL_DESCRIPTION,
                        )
                    # TODO(sweep): figure out why this is breaking
                    # else:
                    #     label = repo.get_label(LABEL_NAME)
                    #     label.edit(
                    #         name=LABEL_NAME,
                    #         color=LABEL_COLOR, 
                    #         description=LABEL_DESCRIPTION
                    #     )

                    current_issue = repo.get_issue(number=request.issue.number)
                    current_issue.add_to_labels(GITHUB_LABEL_NAME)
            case "issues", "labeled":
                request = IssueRequest(**request_dict)
                if 'label' in request_dict and str.lower(request_dict['label']['name']) == GITHUB_LABEL_NAME:
                    request.issue.body = request.issue.body or ""
                    request.repository.description = (
                            request.repository.description or ""
                    )
                    # Update before we handle the ticket to make sure index is up to date
                    # other ways suboptimal
                    handle_ticket.spawn(
                        request.issue.title,
                        request.issue.body,
                        request.issue.number,
                        request.issue.html_url,
                        request.issue.user.login,
                        request.repository.full_name,
                        request.repository.description,
                        request.installation.id,
                        None
                    )
            case "issue_comment", "created":
                request = IssueCommentRequest(**request_dict)
                if request.issue is not None \
                        and GITHUB_LABEL_NAME in [label.name.lower() for label in request.issue.labels] \
                        and request.comment.user.type == "User" \
                        and not (
                            request.issue.pull_request
                            and request.issue.pull_request.url
                        ):
                    logger.info("New issue comment created")
                    request.issue.body = request.issue.body or ""
                    request.repository.description = (
                            request.repository.description or ""
                    )

                    if not request.comment.body.strip().lower().startswith(GITHUB_LABEL_NAME):
                        logger.info("Comment does not start with 'Sweep', passing")
                        return {"success": True, "reason": "Comment does not start with 'Sweep', passing"}

                    # Update before we handle the ticket to make sure index is up to date
                    # other ways suboptimal
                    handle_ticket.spawn(
                        request.issue.title,
                        request.issue.body,
                        request.issue.number,
                        request.issue.html_url,
                        request.issue.user.login,
                        request.repository.full_name,
                        request.repository.description,
                        request.installation.id,
                        request.comment.id
                    )
                elif request.issue.pull_request and request.comment.user.type == "User":  # TODO(sweep): set a limit
                    logger.info(f"Handling comment on PR: {request.issue.pull_request}")
                    g = get_github_client(request.installation.id)
                    repo = g.get_repo(request.repository.full_name)
                    pr = repo.get_pull(request.issue.number)
                    labels = pr.get_labels()
                    comment = request.comment.body
                    if comment.lower().startswith('sweep:') or any(label.name.lower() == "sweep" for label in labels):
                        pr_change_request = PRChangeRequest(
                            type="comment",
                            params={
                                "repo_full_name": request.repository.full_name,
                                "repo_description": request.repository.description,
                                "comment": request.comment.body,
                                "pr_path": None,
                                "pr_line_position": None,
                                "username": request.comment.user.login,
                                "installation_id": request.installation.id,
                                "pr_number": request.issue.number,
                                "comment_id": request.comment.id,
                                "g": g,
                                "repo": repo,
                                "pr": pr,
                            }
                        )
                        push_to_queue(
                            repo_full_name=request.repository.full_name,
                            pr_id=request.issue.number,
                            pr_change_request=pr_change_request
                        )
            case "pull_request_review_comment", "created":
                # Add a separate endpoint for this
                print(request_dict)
                request = CommentCreatedRequest(**request_dict)
                logger.info(f"Handling comment on PR: {request.pull_request.number}")
                g = get_github_client(request.installation.id)
                repo = g.get_repo(request.repository.full_name)
                pr = repo.get_pull(request.pull_request.number)
                labels = pr.get_labels()
                comment = request.comment.body
                if comment.lower().startswith('sweep:') or any(label.name.lower() == "sweep" for label in labels):
                    print(request_dict)
                    pr_change_request = PRChangeRequest(
                        type="comment",
                        params={
                            "repo_full_name": request.repository.full_name,
                            "repo_description": request.repository.description,
                            "comment": request.comment.body,
                            "pr_path": request.comment.path,
                            "pr_line_position": request.comment.original_line,
                            "username": request.comment.user.login,
                            "installation_id": request.installation.id,
                            "pr_number": request.pull_request.number,
                            "comment_id": request.comment.id,
                            "g": g,
                            "repo": repo,
                            "pr": pr,
                        }
                    )
                    push_to_queue(
                        repo_full_name=request.repository.full_name,
                        pr_id=request.pull_request.number,
                        pr_change_request=pr_change_request
                    )
                # Todo: update index on comments
            case "pull_request_review", "submitted":
                # request = ReviewSubmittedRequest(**request_dict)
                pass
            case "check_run", "completed":
                request = CheckRunCompleted(**request_dict)
                logs = None
                if request.sender.login == GITHUB_BOT_USERNAME and request.check_run.conclusion == "failure":
                    logs = handle_check_suite.call(request)
                    if len(request.check_run.pull_requests) > 0 and logs:
                        pr_change_request = PRChangeRequest(
                            type="comment",
                            params={
                                "repo_full_name": request.repository.full_name,
                                "repo_description": request.repository.description,
                                "comment": "Sweep: " + logs,
                                "pr_path": None,
                                "pr_line_position": None,
                                "username": request.sender.login,
                                "installation_id": request.installation.id,
                                "pr_number": request.check_run.pull_requests[0].number,
                                "comment_id": None,
                            }
                        )
                        push_to_queue(
                            repo_full_name=request.repository.full_name,
                            pr_id=request.check_run.pull_requests[0].number,
                            pr_change_request=pr_change_request
                        )
            case "installation_repositories", "added":
                repos_added_request = ReposAddedRequest(**request_dict)
                metadata = {
                    "installation_id": repos_added_request.installation.id,
                    "repositories": [
                        repo.full_name
                        for repo in repos_added_request.repositories_added
                    ],
                }
                posthog.capture("installation_repositories", "started", properties={
                    **metadata
                })
                for repo in repos_added_request.repositories_added:
                    organization, repo_name = repo.full_name.split("/")
                    posthog.capture(
                        organization,
                        "installed_repository",
                        properties={
                            "repo_name": repo_name,
                            "organization": organization,
                            "repo_full_name": repo.full_name
                        }
                    )
                    index_full_repository(
                        repo.full_name,
                        installation_id=repos_added_request.installation.id,
                    )
            case "installation", "created":
                repos_added_request = InstallationCreatedRequest(**request_dict)
                for repo in repos_added_request.repositories:
                    index_full_repository(
                        repo.full_name,
                        installation_id=repos_added_request.installation.id,
                    )
            case "pull_request", "closed":
                pr_request = PRRequest(**request_dict)
                organization, repo_name = pr_request.repository.full_name.split("/")
                commit_author = pr_request.pull_request.user.login
                merged_by = pr_request.pull_request.merged_by.login if pr_request.pull_request.merged_by else pr_request.pull_request.user.login
                if GITHUB_BOT_USERNAME == commit_author:
                    event_name = "merged_sweep_pr"
                    if pr_request.pull_request.title.startswith("[config]"):
                        event_name = "config_pr_merged"
                    posthog.capture(
                        merged_by,
                        event_name,
                        properties={
                            "repo_name": repo_name,
                            "organization": organization,
                            "repo_full_name": pr_request.repository.full_name,
                            "username": merged_by
                        })
                update_index.spawn(
                    request_dict["repository"]["full_name"],
                    installation_id=request_dict["installation"]["id"],
                )
            case "push", None:
                if event != "pull_request" or request_dict["base"]["merged"] == True:
                    update_index.spawn(
                        request_dict["repository"]["full_name"],
                        installation_id=request_dict["installation"]["id"],
                    )
            case "ping", None:
                return {"message": "pong"}
            case _:
                logger.info(
                    f"Unhandled event: {event} {request_dict.get('action', None)}"
                )
    except ValidationError as e:
        logger.warning(f"Failed to parse request: {e}")
        raise HTTPException(status_code=422, detail="Failed to parse request")
    return {"success": True}
