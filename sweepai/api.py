# Do not save logs for main process
import json

from logn import logger
from sweepai.utils.buttons import check_button_activated
from sweepai.utils.safe_pqueue import SafePriorityQueue

logger.init(
    metadata=None,
    create_file=False,
)

import ctypes
from queue import Queue
import sys
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
import requests

from sweepai.config.client import (
    SweepConfig,
    get_documentation_dict,
    RESTART_SWEEP_BUTTON,
    SWEEP_GOOD_FEEDBACK,
    SWEEP_BAD_FEEDBACK,
)
from sweepai.config.server import (
    API_MODAL_INST_NAME,
    BOT_TOKEN_NAME,
    DB_MODAL_INST_NAME,
    DOCS_MODAL_INST_NAME,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_COLOR,
    GITHUB_LABEL_DESCRIPTION,
    GITHUB_LABEL_NAME,
    DISCORD_FEEDBACK_WEBHOOK_URL,
    WHITELISTED_USERS,
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
    PREdited,
    GithubRequest,
)
from sweepai.handlers.create_pr import create_gha_pr, add_config_to_top_repos  # type: ignore
from sweepai.handlers.on_check_suite import on_check_suite  # type: ignore
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_merge import on_merge
from sweepai.handlers.on_ticket import on_ticket
from sweepai.redis_init import redis_client
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo, get_github_client
from sweepai.utils.search_utils import index_full_repository

app = FastAPI()

import tracemalloc

tracemalloc.start()

events = {}
on_ticket_events = {}


def run_on_ticket(*args, **kwargs):
    logger.init(
        metadata={
            **kwargs,
            "name": "ticket_" + kwargs["username"],
        },
        create_file=False,
    )
    with logger:
        on_ticket(*args, **kwargs)


def run_on_comment(*args, **kwargs):
    logger.init(
        metadata={
            **kwargs,
            "name": "comment_" + kwargs["username"],
        },
        create_file=False,
    )

    with logger:
        on_comment(*args, **kwargs)


def run_on_merge(*args, **kwargs):
    logger.init(
        metadata={
            **kwargs,
            "name": "merge_" + args[0]["pusher"]["name"],
        },
        create_file=False,
    )
    with logger:
        on_merge(*args, **kwargs)


def run_on_write_docs(*args, **kwargs):
    logger.init(
        metadata={
            **kwargs,
            "name": "docs_scrape",
        },
        create_file=False,
    )
    with logger:
        write_documentation(*args, **kwargs)


def run_on_check_suite(*args, **kwargs):
    logger.init(
        metadata={
            "name": "check",
        },
        create_file=False,
    )

    request = kwargs["request"]
    pr_change_request = on_check_suite(request)
    if pr_change_request:
        logger.init(
            metadata={
                **pr_change_request.params,
                "name": "check_" + pr_change_request.params["username"],
            },
            create_file=False,
        )
        with logger:
            call_on_comment(**pr_change_request.params, comment_type="github_action")
        logger.info("Done with on_check_suite")
    else:
        logger.info("Skipping on_check_suite as no pr_change_request was returned")


def run_get_deeplake_vs_from_repo(*args, **kwargs):
    logger.init(
        metadata={
            **kwargs,
            "name": "deeplake",
        },
        create_file=False,
    )
    with logger:
        get_deeplake_vs_from_repo(*args, **kwargs)


def terminate_thread(thread):
    """Terminate a python threading.Thread."""
    try:
        if not thread.is_alive():
            return

        exc = ctypes.py_object(SystemExit)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(thread.ident), exc
        )
        if res == 0:
            raise ValueError("Invalid thread ID")
        elif res != 1:
            # Call with exception set to 0 is needed to cleanup properly.
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
            raise SystemError("PyThreadState_SetAsyncExc failed")
    except SystemExit:
        raise SystemExit
    except Exception as e:
        logger.error(f"Failed to terminate thread: {e}")


def call_on_ticket(*args, **kwargs):
    global on_ticket_events
    key = f"{kwargs['repo_full_name']}-{kwargs['issue_number']}"  # Full name, issue number as key

    # Use multithreading
    # Check if a previous process exists for the same key, cancel it
    e = on_ticket_events.get(key, None)
    if e:
        logger.info(f"Found previous thread for key {key} and cancelling it")
        terminate_thread(e)

    thread = threading.Thread(target=run_on_ticket, args=args, kwargs=kwargs)
    on_ticket_events[key] = thread
    thread.start()


def call_on_check_suite(*args, **kwargs):
    repo_full_name = kwargs["request"].repository.full_name
    pr_number = kwargs["request"].check_run.pull_requests[0].number
    key = f"{repo_full_name}-{pr_number}"
    thread = threading.Thread(target=run_on_check_suite, args=args, kwargs=kwargs)
    thread.start()


def call_on_comment(
    *args, **kwargs
):  # TODO: if its a GHA delete all previous GHA and append to the end
    def worker():
        while not events[key].empty():
            task_args, task_kwargs = events[key].get()
            run_on_comment(*task_args, **task_kwargs)

    global events
    repo_full_name = kwargs["repo_full_name"]
    pr_id = kwargs["pr_number"]
    key = f"{repo_full_name}-{pr_id}"  # Full name, comment number as key

    comment_type = kwargs["comment_type"]
    priority = (
        0 if comment_type == "comment" else 1
    )  # set priority to 0 if comment, 1 if GHA
    logger.info(f"Received comment type: {comment_type}")

    if key not in events:
        events[key] = SafePriorityQueue()

    events[key].put(priority, (args, kwargs))

    # If a thread isn't running, start one
    if not any(
        thread.name == key and thread.is_alive() for thread in threading.enumerate()
    ):
        thread = threading.Thread(target=worker, name=key)
        thread.start()


def call_on_merge(*args, **kwargs):
    thread = threading.Thread(target=run_on_merge, args=args, kwargs=kwargs)
    thread.start()


def call_on_write_docs(*args, **kwargs):
    thread = threading.Thread(target=run_on_write_docs, args=args, kwargs=kwargs)
    thread.start()


def call_get_deeplake_vs_from_repo(*args, **kwargs):
    thread = threading.Thread(
        target=run_get_deeplake_vs_from_repo, args=args, kwargs=kwargs
    )
    thread.start()


@app.get("/health")
def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "UP", "port": sys.argv[-1] if len(sys.argv) > 0 else -1},
    )


@app.get("/", response_class=HTMLResponse)
def home():
    return "<h2>Sweep Webhook is up and running! To get started, copy the URL into the GitHub App settings' webhook field.</h2>"


@app.post("/")
async def webhook(raw_request: Request):
    # Do not create logs for api
    logger.init(
        metadata=None,
        create_file=False,
    )

    """Handle a webhook request from GitHub."""
    try:
        request_dict = await raw_request.json()
        event = raw_request.headers.get("X-GitHub-Event")
        assert event is not None

        # # Check if user is in Whitelist
        # gh_request = GithubRequest(**request_dict)
        # if (
        #     WHITELISTED_USERS is not None
        #     and len(WHITELISTED_USERS) > 0
        #     and gh_request.sender is not None
        #     and gh_request.sender.login not in WHITELISTED_USERS
        # ):
        #     return {
        #         "success": True,
        #         "reason": "User not in whitelist",
        #     }

        action = request_dict.get("action", None)
        # logger.bind(event=event, action=action)
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
                    current_issue = repo.get_issue(number=request.issue.number)
                    current_issue.add_to_labels(GITHUB_LABEL_NAME)
            case "issue_comment", "edited":
                request = IssueCommentRequest(**request_dict)

                restart_sweep = False
                if (
                    request.comment.user.type == "Bot"
                    and GITHUB_BOT_USERNAME in request.comment.user.login
                    and request.changes.body_from is not None
                    and check_button_activated(
                        RESTART_SWEEP_BUTTON, request.comment.body, request.changes
                    )
                    and GITHUB_LABEL_NAME
                    in [label.name.lower() for label in request.issue.labels]
                    and request.sender.type == "User"
                ):
                    # Restart Sweep on this issue
                    restart_sweep = True

                if (
                    request.issue is not None
                    and GITHUB_LABEL_NAME
                    in [label.name.lower() for label in request.issue.labels]
                    and request.comment.user.type == "User"
                    and not request.comment.user.login.startswith("sweep")
                    and not (
                        request.issue.pull_request and request.issue.pull_request.url
                    )
                    or restart_sweep
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
                        and not restart_sweep
                    ):
                        logger.info("Comment does not start with 'Sweep', passing")
                        return {
                            "success": True,
                            "reason": "Comment does not start with 'Sweep', passing",
                        }

                    # Update before we handle the ticket to make sure index is up to date
                    # other ways suboptimal

                    key = (request.repository.full_name, request.issue.number)

                    call_on_ticket(
                        title=request.issue.title,
                        summary=request.issue.body,
                        issue_number=request.issue.number,
                        issue_url=request.issue.html_url,
                        username=request.issue.user.login,
                        repo_full_name=request.repository.full_name,
                        repo_description=request.repository.description,
                        installation_id=request.installation.id,
                        comment_id=request.comment.id if not restart_sweep else None,
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
                            params={
                                "comment_type": "comment",
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
                        # push_to_queue(
                        #     repo_full_name=request.repository.full_name,
                        #     pr_id=request.issue.number,
                        #     pr_change_request=pr_change_request,
                        # )
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
                        title=request.issue.title,
                        summary=request.issue.body,
                        issue_number=request.issue.number,
                        issue_url=request.issue.html_url,
                        username=request.issue.user.login,
                        repo_full_name=request.repository.full_name,
                        repo_description=request.repository.description,
                        installation_id=request.installation.id,
                        comment_id=None,
                    )
                else:
                    logger.info("Issue edited, but not a sweep issue")
            case "issues", "labeled":
                request = IssueRequest(**request_dict)
                if any(
                    label.name.lower() == GITHUB_LABEL_NAME
                    for label in request.issue.labels
                ):
                    request.issue.body = request.issue.body or ""
                    request.repository.description = (
                        request.repository.description or ""
                    )
                    call_on_ticket(
                        title=request.issue.title,
                        summary=request.issue.body,
                        issue_number=request.issue.number,
                        issue_url=request.issue.html_url,
                        username=request.issue.user.login,
                        repo_full_name=request.repository.full_name,
                        repo_description=request.repository.description,
                        installation_id=request.installation.id,
                        comment_id=None,
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
                        title=request.issue.title,
                        summary=request.issue.body,
                        issue_number=request.issue.number,
                        issue_url=request.issue.html_url,
                        username=request.issue.user.login,
                        repo_full_name=request.repository.full_name,
                        repo_description=request.repository.description,
                        installation_id=request.installation.id,
                        comment_id=request.comment.id,
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
                            params={
                                "comment_type": "comment",
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
                        params={
                            "comment_type": "comment",
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
                    pr = repo.get_pull(pull_requests[0].number)
                    if GITHUB_LABEL_NAME in [label.name.lower() for label in pr.labels]:
                        call_on_check_suite(request=request)
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
                except SystemExit:
                    raise SystemExit
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
                except SystemExit:
                    raise SystemExit
                except Exception as e:
                    logger.error(f"Failed to add config to top repos: {e}")

                # Index all repos
                for repo in repos_added_request.repositories:
                    index_full_repository(
                        repo.full_name,
                        installation_id=repos_added_request.installation.id,
                    )
            case "pull_request", "edited":
                request = PREdited(**request_dict)

                if (
                    request.pull_request.user.login == GITHUB_BOT_USERNAME
                    and not request.sender.login.endswith("[bot]")
                    and DISCORD_FEEDBACK_WEBHOOK_URL is not None
                ):
                    good_button = check_button_activated(
                        SWEEP_GOOD_FEEDBACK, request.pull_request.body, request.changes
                    )
                    bad_button = check_button_activated(
                        SWEEP_BAD_FEEDBACK, request.pull_request.body, request.changes
                    )

                    if good_button or bad_button:
                        emoji = "😕"
                        if good_button:
                            emoji = "👍"
                        elif bad_button:
                            emoji = "👎"
                        data = {
                            "content": f"{emoji} {request.pull_request.html_url} ({request.sender.login})\n{request.pull_request.commits} commits, {request.pull_request.changed_files} files: +{request.pull_request.additions}, -{request.pull_request.deletions}"
                        }
                        headers = {"Content-Type": "application/json"}
                        response = requests.post(
                            DISCORD_FEEDBACK_WEBHOOK_URL,
                            data=json.dumps(data),
                            headers=headers,
                        )

                        # Send feedback to PostHog
                        posthog.capture(
                            request.sender.login,
                            "feedback",
                            properties={
                                "repo_name": request.repository.full_name,
                                "pr_url": request.pull_request.html_url,
                                "pr_commits": request.pull_request.commits,
                                "pr_additions": request.pull_request.additions,
                                "pr_deletions": request.pull_request.deletions,
                                "pr_changed_files": request.pull_request.changed_files,
                                "username": request.sender.login,
                                "good_button": good_button,
                                "bad_button": bad_button,
                            },
                        )

                        def remove_buttons_from_description(body):
                            """
                            Replace:
                            ### PR Feedback...
                            ...
                            # (until it hits the next #)

                            with
                            ### PR Feedback: {emoji}
                            #
                            """
                            lines = body.split("\n")
                            if not lines[0].startswith("### PR Feedback"):
                                return None
                            # Find when the second # occurs
                            i = 0
                            for i, line in enumerate(lines):
                                if line.startswith("#") and i > 0:
                                    break

                            return "\n".join(
                                [
                                    f"### PR Feedback: {emoji}",
                                    *lines[i:],
                                ]
                            )

                        # Update PR description to remove buttons
                        try:
                            _, g = get_github_client(request.installation.id)
                            repo = g.get_repo(request.repository.full_name)
                            pr = repo.get_pull(request.pull_request.number)
                            new_body = remove_buttons_from_description(
                                request.pull_request.body
                            )
                            if new_body is not None:
                                pr.edit(body=new_body)
                        except SystemExit:
                            raise SystemExit
                        except Exception as e:
                            logger.error(f"Failed to edit PR description: {e}")
                    pass
                pass
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
                    # on merge
                    call_on_merge(request_dict, chat_logger)
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
                            call_on_write_docs(doc_url)
                    # this makes it faster for everyone because the queue doesn't get backed up
                    if chat_logger.is_paying_user():
                        cloned_repo = ClonedRepo(
                            request_dict["repository"]["full_name"],
                            installation_id=request_dict["installation"]["id"],
                        )
                        call_get_deeplake_vs_from_repo(cloned_repo)
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
    except SystemExit:
        raise SystemExit
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
            except SystemExit:
                raise SystemExit
            except Exception as e:
                logger.error(
                    f"Failed to merge changes from default branch into PR #{pr.number}: {e}"
                )
    except SystemExit:
        raise SystemExit
    except:
        logger.warning("Failed to update sweep PRs")
