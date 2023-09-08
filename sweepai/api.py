import sys

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger
from pydantic import ValidationError

from sweepai.celery_init import celery_app
from sweepai.config.client import SweepConfig, get_documentation_dict
from sweepai.config.server import (
    API_MODAL_INST_NAME,
    BOT_TOKEN_NAME,
    DB_MODAL_INST_NAME,
    DOCS_MODAL_INST_NAME,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_COLOR,
    GITHUB_LABEL_DESCRIPTION,
    GITHUB_LABEL_NAME,
)
from sweepai.core.documentation import write_documentation
from sweepai.core.entities import PRChangeRequest, SweepContext
from sweepai.core.vector_db import get_deeplake_vs_from_repo
from sweepai.events import (
    CheckRunCompleted,
    CommentCreatedRequest,
    InstallationCreatedRequest,
    IssueCommentRequest,
    IssueRequest,
    PRRequest,
    ReposAddedRequest,
)
from sweepai.handlers.create_pr import create_gha_pr, add_config_to_top_repos  # type: ignore
from sweepai.handlers.create_pr import create_pr_changes, safe_delete_sweep_branch
from sweepai.handlers.on_check_suite import on_check_suite  # type: ignore
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_ticket import on_ticket
from sweepai.redis_init import redis_client
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.search_utils import index_full_repository

app = FastAPI()

import tracemalloc

tracemalloc.start()


@celery_app.task(bind=True)
def run_ticket(self, *args, **kwargs):
    logger.info(f"Running on_ticket Task ID: {self.request.id}")
    on_ticket(*args, **kwargs)
    logger.info("Done with on_ticket")


@celery_app.task(bind=True)
def run_comment(self, *args, **kwargs):
    logger.info(f"Running on_comment Task ID: {self.request.id}")
    on_comment(*args, **kwargs)
    logger.info("Done with on_comment")


def call_on_ticket(*args, **kwargs):
    key = f"{args[5]}-{args[2]}"  # Full name, issue number as key
    # Check if a previous process exists for the same key, cancel it
    prev_task_id = redis_client.get(key)
    prev_task_id = prev_task_id.decode("utf-8") if prev_task_id else None
    i = celery_app.control.inspect()
    # To get a list of active tasks:
    active_tasks = i.active()
    logger.info(f"Active tasks: {active_tasks}")
    if prev_task_id:
        logger.info(f"Found previous task id: {prev_task_id} and cancelling it")
        result = celery_app.control.revoke(prev_task_id)  # Decoding bytes to string
        logger.info(f"Result of cancelling: {result}")
        redis_client.delete(key)
    else:
        logger.info(f"No previous task id found for key {key}")
    task = celery_app.send_task("sweepai.api.run_ticket", args=args, kwargs=kwargs)
    logger.info(f"Saving task id {task.id} for key {key}")
    redis_client.set(key, task.id)
    active_tasks = i.active()
    logger.info(f"Active tasks: {active_tasks}")


def call_on_comment(*args, **kwargs):
    repo_full_name = kwargs["repo_full_name"]
    pr_id = kwargs["pr_number"]
    key = f"{repo_full_name}-{pr_id}"  # Full name, comment number as key

    i = celery_app.control.inspect()
    active_tasks = i.active()
    logger.info(f"Active tasks: {active_tasks}")

    # Get previous task IDs for the same key, if any
    prev_task_ids = redis_client.lrange(key, 0, -1)
    prev_task_ids = (
        [task_id.decode("utf-8") for task_id in prev_task_ids] if prev_task_ids else []
    )

    # If previous tasks are pending, don't enqueue new task
    for prev_task_id in prev_task_ids:
        task_status = AsyncResult(prev_task_id, app=celery_app).status
        if task_status not in ("SUCCESS", "FAILURE"):
            logger.info(
                f"Previous task id {prev_task_id} still pending. Not enqueuing new task."
            )

    # Enqueue new task and save task ID
    task = celery_app.send_task("sweepai.api.run_comment", args=args, kwargs=kwargs)
    logger.info(f"Enqueuing new task id {task.id} for key {key}")

    # Save the new task ID to the list
    redis_client.rpush(key, task.id)


@app.get("/health")
def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "UP", "port": sys.argv[-1] if len(sys.argv) > 0 else -1},
    )


@app.get("/", response_class=HTMLResponse)
def home():
    return "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>"


"""
def push_to_queue(repo_full_name: str, pr_id: int, pr_change_request: PRChangeRequest):
    logger.info(f"Pushing to queue: {repo_full_name}, {pr_id}, {pr_change_request}")
    key = (repo_full_name, pr_id)
    call_id, queue = stub.pr_queues[key] if key in stub.pr_queues else ("0", [])
    function_is_completed = function_call_is_completed(call_id)
    if pr_change_request.type == "comment" or function_is_completed:
        queue = [pr_change_request] + queue
        if function_is_completed:
            stub.pr_queues[key] = ("0", queue)
            call_id = handle_pr_change_request.spawn(
                repo_full_name=repo_full_name, pr_id=pr_id
            ).object_id
        stub.pr_queues[key] = (call_id, queue)
"""


def push_to_queue(repo_full_name: str, pr_id: int, pr_change_request: PRChangeRequest):
    key = f"{repo_full_name}-{pr_id}"  # Full name, issue number as key
    # Check if a previous process exists for the same key, cancel it

    pass


@app.post("/")
async def webhook(raw_request: Request):
    """Handle a webhook request from GitHub."""
    try:
        request_dict = await raw_request.json()
        logger.info(f"Received request: {request_dict.keys()}")
        event = raw_request.headers.get("X-GitHub-Event")
        assert event is not None
        action = request_dict.get("action", None)
        logger.bind(event=event, action=action)
        logger.info(f"Received event: {event}, {action}")
        match event, action:
            case "issues", "opened":
                request = IssueRequest(**request_dict)
                issue_title_lower = request.issue.title.lower()
                if (
                    issue_title_lower.startswith("sweep")
                    or "sweep:" in issue_title_lower
                ):
                    _, g = get_github_client(request.installation.id)
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
            case "issue_comment", "edited":
                request = IssueCommentRequest(**request_dict)
                if (
                    request.issue is not None
                    and GITHUB_LABEL_NAME
                    in [label.name.lower() for label in request.issue.labels]
                    and request.comment.user.type == "User"
                    and not request.comment.user.login.startswith("sweep")
                    and not (
                        request.issue.pull_request and request.issue.pull_request.url
                    )
                ):
                    logger.info("New issue comment edited")
                    request.issue.body = request.issue.body or ""
                    request.repository.description = (
                        request.repository.description or ""
                    )

                    if (
                        not request.comment.body.strip()
                        .lower()
                        .startswith(GITHUB_LABEL_NAME)
                    ):
                        logger.info("Comment does not start with 'Sweep', passing")
                        return {
                            "success": True,
                            "reason": "Comment does not start with 'Sweep', passing",
                        }

                    # Update before we handle the ticket to make sure index is up to date
                    # other ways suboptimal

                    key = (request.repository.full_name, request.issue.number)
                    # logger.info(f"Checking if {key} is in {stub.issue_lock}")
                    # process = stub.issue_lock[key] if key in stub.issue_lock else None
                    # if process:
                    #     logger.info("Cancelling process")
                    #     process.cancel()
                    # stub.issue_lock[
                    # print(issue_locks)
                    #     (request.repository.full_name, request.issue.number)
                    # ] =
                    #

                    call_on_ticket(
                        request.issue.title,
                        request.issue.body,
                        request.issue.number,
                        request.issue.html_url,
                        request.issue.user.login,
                        request.repository.full_name,
                        request.repository.description,
                        request.installation.id,
                        request.comment.id,
                        edited=True,
                    )
                elif (
                    request.issue.pull_request and request.comment.user.type == "User"
                ):  # TODO(sweep): set a limit
                    logger.info(f"Handling comment on PR: {request.issue.pull_request}")
                    _, g = get_github_client(request.installation.id)
                    repo = g.get_repo(request.repository.full_name)
                    pr = repo.get_pull(request.issue.number)
                    labels = pr.get_labels()
                    comment = request.comment.body
                    if comment.lower().startswith("sweep:") or any(
                        label.name.lower() == "sweep" for label in labels
                    ):
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
                            },
                        )
                        push_to_queue(
                            repo_full_name=request.repository.full_name,
                            pr_id=request.issue.number,
                            pr_change_request=pr_change_request,
                        )
            case "issues", "edited":
                request = IssueRequest(**request_dict)
                if (
                    GITHUB_LABEL_NAME
                    in [label.name.lower() for label in request.issue.labels]
                    and request.sender.type == "User"
                    and not request.sender.login.startswith("sweep")
                ):
                    logger.info("New issue edited")
                    key = (request.repository.full_name, request.issue.number)
                    # logger.info(f"Checking if {key} is in {stub.issue_lock}")
                    # process = stub.issue_lock[key] if key in stub.issue_lock else None
                    # if process:
                    #     logger.info("Cancelling process")
                    #     process.cancel()
                    # stub.issue_lock[
                    #     (request.repository.full_name, request.issue.number)
                    # ] =
                    call_on_ticket(
                        request.issue.title,
                        request.issue.body,
                        request.issue.number,
                        request.issue.html_url,
                        request.issue.user.login,
                        request.repository.full_name,
                        request.repository.description,
                        request.installation.id,
                        None,
                    )
                else:
                    logger.info("Issue edited, but not a sweep issue")
            case "issues", "labeled":
                request = IssueRequest(**request_dict)
                if (
                    "label" in request_dict
                    and str.lower(request_dict["label"]["name"]) == GITHUB_LABEL_NAME
                ):
                    request.issue.body = request.issue.body or ""
                    request.repository.description = (
                        request.repository.description or ""
                    )
                    # Update before we handle the ticket to make sure index is up to date
                    # other ways suboptimal
                    key = (request.repository.full_name, request.issue.number)
                    # logger.info(f"Checking if {key} is in {stub.issue_lock}")
                    # process = stub.issue_lock[key] if key in stub.issue_lock else None
                    # if process:
                    #     logger.info("Cancelling process")
                    #     process.cancel()
                    # stub.issue_lock[
                    #     (request.repository.full_name, request.issue.number)
                    # ] =
                    call_on_ticket(
                        request.issue.title,
                        request.issue.body,
                        request.issue.number,
                        request.issue.html_url,
                        request.issue.user.login,
                        request.repository.full_name,
                        request.repository.description,
                        request.installation.id,
                        None,
                    )
            case "issue_comment", "created":
                request = IssueCommentRequest(**request_dict)
                if (
                    request.issue is not None
                    and GITHUB_LABEL_NAME
                    in [label.name.lower() for label in request.issue.labels]
                    and request.comment.user.type == "User"
                    and not (
                        request.issue.pull_request and request.issue.pull_request.url
                    )
                ):
                    logger.info("New issue comment created")
                    request.issue.body = request.issue.body or ""
                    request.repository.description = (
                        request.repository.description or ""
                    )

                    if (
                        not request.comment.body.strip()
                        .lower()
                        .startswith(GITHUB_LABEL_NAME)
                    ):
                        logger.info("Comment does not start with 'Sweep', passing")
                        return {
                            "success": True,
                            "reason": "Comment does not start with 'Sweep', passing",
                        }

                    # Update before we handle the ticket to make sure index is up to date
                    # other ways suboptimal
                    key = (request.repository.full_name, request.issue.number)
                    # logger.info(f"Checking if {key} is in {stub.issue_lock}")
                    # process = stub.issue_lock[key] if key in stub.issue_lock else None
                    # if process:
                    #     logger.info("Cancelling process")
                    #     process.cancel()
                    # stub.issue_lock[
                    #     (request.repository.full_name, request.issue.number)
                    # ] =
                    call_on_ticket(
                        request.issue.title,
                        request.issue.body,
                        request.issue.number,
                        request.issue.html_url,
                        request.issue.user.login,
                        request.repository.full_name,
                        request.repository.description,
                        request.installation.id,
                        request.comment.id,
                    )
                elif (
                    request.issue.pull_request and request.comment.user.type == "User"
                ):  # TODO(sweep): set a limit
                    logger.info(f"Handling comment on PR: {request.issue.pull_request}")
                    _, g = get_github_client(request.installation.id)
                    repo = g.get_repo(request.repository.full_name)
                    pr = repo.get_pull(request.issue.number)
                    labels = pr.get_labels()
                    comment = request.comment.body
                    if comment.lower().startswith("sweep:") or any(
                        label.name.lower() == "sweep" for label in labels
                    ):
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
                            },
                        )
                        call_on_comment(**pr_change_request.params)
                        push_to_queue(
                            repo_full_name=request.repository.full_name,
                            pr_id=request.issue.number,
                            pr_change_request=pr_change_request,
                        )
            case "pull_request_review_comment", "created":
                # Add a separate endpoint for this
                request = CommentCreatedRequest(**request_dict)
                logger.info(f"Handling comment on PR: {request.pull_request.number}")
                _, g = get_github_client(request.installation.id)
                repo = g.get_repo(request.repository.full_name)
                pr = repo.get_pull(request.pull_request.number)
                labels = pr.get_labels()
                comment = request.comment.body
                if (
                    comment.lower().startswith("sweep:")
                    or any(label.name.lower() == "sweep" for label in labels)
                ) and request.comment.user.type == "User":
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
                        },
                    )
                    call_on_comment(**pr_change_request.params)
                    push_to_queue(
                        repo_full_name=request.repository.full_name,
                        pr_id=request.pull_request.number,
                        pr_change_request=pr_change_request,
                    )
                # Todo: update index on comments
            case "pull_request_review", "submitted":
                # request = ReviewSubmittedRequest(**request_dict)
                pass
            case "check_run", "completed":
                request = CheckRunCompleted(**request_dict)
                logger.info(f"Handling check suite for {request.repository.full_name}")
                _, g = get_github_client(request.installation.id)
                repo = g.get_repo(request.repository.full_name)
                pull_requests = request.check_run.pull_requests
                if pull_requests:
                    # TODO: why does this error? try/catch to handle github requests
                    try:
                        pull_request = repo.get_pull(
                            request.check_run.pull_requests[0].number
                        )
                        if (
                            len(request.check_run.pull_requests) > 0
                            and pull_request.user.login.lower().startswith("sweep")
                            and request.check_run.conclusion == "failure"
                            and not pull_request.title.startswith("[DRAFT]")
                            and pull_request.labels
                            and any(
                                label.name.lower() == "sweep"
                                for label in pull_request.labels
                            )
                        ):
                            logger.info("Handling check suite")
                            pr_change_request = PRChangeRequest(
                                type="gha", params={"request": request}
                            )
                            push_to_queue(
                                repo_full_name=request.repository.full_name,
                                pr_id=request.check_run.pull_requests[0].number,
                                pr_change_request=pr_change_request,
                            )
                        else:
                            logger.info(
                                "Skipping check suite for"
                                f" {request.repository.full_name} because it is not a failure"
                                " or not from the bot or is a draft"
                            )
                    except Exception as e:
                        print("FAILED check_run completed")
                        logger.error(f"Failed to handle check suite: {e}")
                else:
                    logger.info("No pull requests, passing")
            case "installation_repositories", "added":
                repos_added_request = ReposAddedRequest(**request_dict)
                metadata = {
                    "installation_id": repos_added_request.installation.id,
                    "repositories": [
                        repo.full_name
                        for repo in repos_added_request.repositories_added
                    ],
                }

                try:
                    add_config_to_top_repos(
                        repos_added_request.installation.id,
                        repos_added_request.installation.account.login,
                        repos_added_request.repositories_added,
                    )
                except Exception as e:
                    logger.error(f"Failed to add config to top repos: {e}")

                posthog.capture(
                    "installation_repositories", "started", properties={**metadata}
                )
                for repo in repos_added_request.repositories_added:
                    organization, repo_name = repo.full_name.split("/")
                    posthog.capture(
                        organization,
                        "installed_repository",
                        properties={
                            "repo_name": repo_name,
                            "organization": organization,
                            "repo_full_name": repo.full_name,
                        },
                    )
                    index_full_repository(
                        repo.full_name,
                        installation_id=repos_added_request.installation.id,
                    )
            case "installation", "created":
                repos_added_request = InstallationCreatedRequest(**request_dict)

                try:
                    add_config_to_top_repos(
                        repos_added_request.installation.id,
                        repos_added_request.installation.account.login,
                        repos_added_request.repositories,
                    )
                except Exception as e:
                    logger.error(f"Failed to add config to top repos: {e}")

                # Index all repos
                for repo in repos_added_request.repositories:
                    index_full_repository(
                        repo.full_name,
                        installation_id=repos_added_request.installation.id,
                    )
            case "pull_request", "closed":
                pr_request = PRRequest(**request_dict)
                organization, repo_name = pr_request.repository.full_name.split("/")
                commit_author = pr_request.pull_request.user.login
                merged_by = (
                    pr_request.pull_request.merged_by.login
                    if pr_request.pull_request.merged_by
                    else None
                )
                if GITHUB_BOT_USERNAME == commit_author and merged_by is not None:
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
                            "username": merged_by,
                            "additions": pr_request.pull_request.additions,
                            "deletions": pr_request.pull_request.deletions,
                            "total_changes": pr_request.pull_request.additions
                            + pr_request.pull_request.deletions,
                        },
                    )
                chat_logger = ChatLogger({"username": merged_by})
                # this makes it faster for everyone because the queue doesn't get backed up
                # active users also should not see a delay

                # Todo: fix update index for pro users
                # if chat_logger.is_paying_user():
                #     update_index(
                #         request_dict["repository"]["full_name"],
                #         installation_id=request_dict["installation"]["id"],
                #     )
            case "push", None:
                if event != "pull_request" or request_dict["base"]["merged"] == True:
                    chat_logger = ChatLogger(
                        {"username": request_dict["pusher"]["name"]}
                    )
                    if request_dict["head_commit"] and (
                        "sweep.yaml" in request_dict["head_commit"]["added"]
                        or "sweep.yaml" in request_dict["head_commit"]["modified"]
                    ):
                        _, g = get_github_client(request_dict["installation"]["id"])
                        repo = g.get_repo(request_dict["repository"]["full_name"])
                        docs = get_documentation_dict(repo)
                        logger.info(f"Sweep.yaml docs: {docs}")
                        # Call the write_documentation function for each of the existing fields in the "docs" mapping
                        for doc_url, _ in docs.values():
                            logger.info(f"Writing documentation for {doc_url}")
                            write_documentation(doc_url)
                    # this makes it faster for everyone because the queue doesn't get backed up
                    if chat_logger.is_paying_user():
                        cloned_repo = ClonedRepo(
                            request_dict["repository"]["full_name"],
                            installation_id=request_dict["installation"]["id"],
                        )
                        get_deeplake_vs_from_repo(cloned_repo)
                    update_sweep_prs(
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


# Set up cronjob for this
@app.get("/update_sweep_prs")
def update_sweep_prs(repo_full_name: str, installation_id: int):
    # Get a Github client
    _, g = get_github_client(installation_id)

    # Get the repository
    repo = g.get_repo(repo_full_name)
    config = SweepConfig.get_config(repo)

    try:
        branch_ttl = int(config.get("branch_ttl", 7))
    except:
        branch_ttl = 7
    branch_ttl = max(branch_ttl, 1)

    # Get all open pull requests created by Sweep
    pulls = repo.get_pulls(
        state="open", head="sweep", sort="updated", direction="desc"
    )[:5]

    # For each pull request, attempt to merge the changes from the default branch into the pull request branch
    try:
        for pr in pulls:
            try:
                # make sure it's a sweep ticket
                feature_branch = pr.head.ref
                if not feature_branch.startswith(
                    "sweep/"
                ) and not feature_branch.startswith("sweep_"):
                    continue

                repo.merge(
                    feature_branch,
                    repo.default_branch,
                    f"Merge main into {feature_branch}",
                )

                # logger.info(f"Successfully merged changes from default branch into PR #{pr.number}")
                logger.info(
                    f"Merging changes from default branch into PR #{pr.number} for branch"
                    f" {feature_branch}"
                )

                # Check if the merged PR is the config PR
                if pr.title == "Configure Sweep" and pr.merged:
                    # Create a new PR to add "gha_enabled: True" to sweep.yaml
                    create_gha_pr(g, repo)
            except Exception as e:
                logger.error(
                    f"Failed to merge changes from default branch into PR #{pr.number}: {e}"
                )
    except:
        logger.warning("Failed to update sweep PRs")
