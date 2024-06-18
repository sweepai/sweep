from __future__ import annotations

import ctypes
import os
import threading
import time
from typing import Optional

from fastapi import (
    Body,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Request,
)
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer
from fastapi.templating import Jinja2Templates
from github.Commit import Commit
from github import GithubException

from sweepai.config.client import (
    RESTART_SWEEP_BUTTON,
    REVERT_CHANGED_FILES_TITLE,
    RULES_TITLE,
    SweepConfig,
    get_gha_enabled,
)
from sweepai.config.server import (
    BLACKLISTED_USERS,
    DISABLED_REPOS,
    ENV,
    GHA_AUTOFIX_ENABLED,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_COLOR,
    GITHUB_LABEL_DESCRIPTION,
    GITHUB_LABEL_NAME,
    IS_SELF_HOSTED,
    SENTRY_URL,
)
from sweepai.chat.api import app as chat_app
from sweepai.core.entities import PRChangeRequest
from sweepai.global_threads import global_threads
from sweepai.handlers.review_pr import review_pr
from sweepai.handlers.create_pr import (  # type: ignore
    create_gha_pr,
)
from sweepai.handlers.on_button_click import handle_button_click
from sweepai.handlers.on_check_suite import (  # type: ignore
    clean_gh_logs,
    download_logs,
)
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_jira_ticket import handle_jira_ticket
from sweepai.handlers.on_ticket import on_ticket
from sweepai.utils.buttons import (
    check_button_activated,
    check_button_title_match,
)
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import logger, posthog
from sweepai.utils.github_utils import CURRENT_USERNAME, get_github_client
from sweepai.utils.hash import verify_signature
from sweepai.utils.progress import TicketProgress
from sweepai.utils.safe_pqueue import SafePriorityQueue
from sweepai.utils.str_utils import BOT_SUFFIX, get_hash
from sweepai.utils.validate_license import validate_license
from sweepai.web.events import (
    CheckRunCompleted,
    CommentCreatedRequest,
    IssueCommentRequest,
    IssueRequest,
    PREdited,
    PRLabeledRequest,
    PRRequest,
)
from sweepai.web.health import health_check
import sentry_sdk
from sentry_sdk import set_user

version = time.strftime("%y.%m.%d.%H")

if SENTRY_URL:
    sentry_sdk.init(
        dsn=SENTRY_URL,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        release=version
    )

app = FastAPI()

app.mount("/chat", chat_app)

events = {}
on_ticket_events = {}
review_pr_events = {}

security = HTTPBearer()

templates = Jinja2Templates(directory="sweepai/web")
logger.bind(application="webhook")

def run_on_ticket(*args, **kwargs):
    tracking_id = get_hash()
    with logger.contextualize(
        **kwargs,
        name="ticket_" + kwargs["username"],
        tracking_id=tracking_id,
    ):
        return on_ticket(*args, **kwargs, tracking_id=tracking_id)


def run_on_comment(*args, **kwargs):
    tracking_id = get_hash()
    with logger.contextualize(
        **kwargs,
        name="comment_" + kwargs["username"],
        tracking_id=tracking_id,
    ):
        on_comment(*args, **kwargs, tracking_id=tracking_id)

def run_review_pr(*args, **kwargs):
    tracking_id = get_hash()
    with logger.contextualize(
        **kwargs,
        name="review_" + kwargs["username"],
        tracking_id=tracking_id,
    ):
        review_pr(*args, **kwargs, tracking_id=tracking_id)


def run_on_button_click(*args, **kwargs):
    thread = threading.Thread(target=handle_button_click, args=args, kwargs=kwargs)
    thread.start()
    global_threads.append(thread)


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
    except Exception as e:
        logger.exception(f"Failed to terminate thread: {e}")


# def delayed_kill(thread: threading.Thread, delay: int = 60 * 60):
#     time.sleep(delay)
#     terminate_thread(thread)


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
    global_threads.append(thread)

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
    logger.info(f"Received comment type: {comment_type}")

    if key not in events:
        events[key] = SafePriorityQueue()

    events[key].put(0, (args, kwargs))

    # If a thread isn't running, start one
    if not any(
        thread.name == key and thread.is_alive() for thread in threading.enumerate()
    ):
        thread = threading.Thread(target=worker, name=key)
        thread.start()
        global_threads.append(thread)

# add a review by sweep on the pr
def call_review_pr(*args, **kwargs):
    global review_pr_events
    key = f"{kwargs['repository'].full_name}-{kwargs['pr'].number}"  # Full name, issue number as key

    # Use multithreading
    # Check if a previous process exists for the same key, cancel it
    e = review_pr_events.get(key, None)
    if e:
        logger.info(f"Found previous thread for key {key} and cancelling it")
        terminate_thread(e)

    thread = threading.Thread(target=run_review_pr, args=args, kwargs=kwargs)
    review_pr_events[key] = thread
    thread.start()
    global_threads.append(thread)


@app.get("/health")
def redirect_to_health():
    return health_check()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        validate_license()
        license_expired = False
    except Exception as e:
        logger.warning(e)
        license_expired = True
    return templates.TemplateResponse(
        name="index.html", context={"version": version, "request": request, "license_expired": license_expired}
    )


@app.get("/ticket_progress/{tracking_id}")
def progress(tracking_id: str = Path(...)):
    ticket_progress = TicketProgress.load(tracking_id)
    return ticket_progress.dict()


def handle_github_webhook(event_payload):
    handle_event(event_payload.get("request"), event_payload.get("event"))


def handle_request(request_dict, event=None):
    """So it can be exported to the listen endpoint."""
    with logger.contextualize(tracking_id="main", env=ENV):
        action = request_dict.get("action")

        try:
            handle_github_webhook(
                {
                    "request": request_dict,
                    "event": event,
                }
            )
        except Exception as e:
            logger.exception(str(e))
        logger.info(f"Done handling {event}, {action}")
        return {"success": True}


# @app.post("/")
async def validate_signature(
    request: Request,
    x_hub_signature: Optional[str] = Header(None, alias="X-Hub-Signature-256")
):
    payload_body = await request.body()
    if not verify_signature(payload_body=payload_body, signature_header=x_hub_signature):
        raise HTTPException(status_code=403, detail="Request signatures didn't match!")

@app.post("/", dependencies=[Depends(validate_signature)])
def webhook(
    request_dict: dict = Body(...),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
):
    """Handle a webhook request from GitHub"""
    with logger.contextualize(tracking_id="main", env=ENV):
        action = request_dict.get("action", None)

        logger.info(f"Received event: {x_github_event}, {action}")
        return handle_request(request_dict, event=x_github_event)

@app.post("/jira")
def jira_webhook(
    request_dict: dict = Body(...),
) -> None:
    def call_jira_ticket(*args, **kwargs):
        thread = threading.Thread(target=handle_jira_ticket, args=args, kwargs=kwargs)
        thread.start()
    call_jira_ticket(event=request_dict)

# Set up cronjob for this
@app.get("/update_sweep_prs_v2")
def update_sweep_prs_v2(repo_full_name: str, installation_id: int):
    # Get a Github client
    _, g = get_github_client(installation_id)

    # Get the repository
    repo = g.get_repo(repo_full_name)
    config = SweepConfig.get_config(repo)

    try:
        branch_ttl = int(config.get("branch_ttl", 7))
    except Exception:
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
                if "Resolve merge conflicts" in pr.title:
                    continue
                if (
                    pr.mergeable_state != "clean"
                    and (time.time() - pr.created_at.timestamp()) > 60 * 60 * 24
                    and pr.title.startswith("[Sweep Rules]")
                ):
                    pr.edit(state="closed")
                    continue

                repo.merge(
                    feature_branch,
                    pr.base.ref,
                    f"Merge main into {feature_branch}",
                )

                # Check if the merged PR is the config PR
                if pr.title == "Configure Sweep" and pr.merged:
                    # Create a new PR to add "gha_enabled: True" to sweep.yaml
                    create_gha_pr(g, repo)
            except Exception as e:
                logger.warning(
                    f"Failed to merge changes from default branch into PR #{pr.number}: {e}"
                )
    except Exception:
        logger.warning("Failed to update sweep PRs")

def should_handle_comment(request: CommentCreatedRequest | IssueCommentRequest):
    comment = request.comment.body
    return (
        (
            comment.lower().startswith("sweep:") # we will handle all comments (with or without label) that start with "sweep:"
        )
        and request.comment.user.type == "User" # ensure it's a user comment
        and request.comment.user.login not in BLACKLISTED_USERS # ensure it's not a blacklisted user
        and BOT_SUFFIX not in comment # we don't handle bot commnents
    )

def handle_event(request_dict, event):
    action = request_dict.get("action")
    
    username = request_dict.get("sender", {}).get("login")
    if username:
        set_user({"username": username})

    if repo_full_name := request_dict.get("repository", {}).get("full_name"):
        if repo_full_name in DISABLED_REPOS:
            logger.warning(f"Repo {repo_full_name} is disabled")
            return {"success": False, "error_message": "Repo is disabled"}

    with logger.contextualize(tracking_id="main", env=ENV):
        match event, action:
            case "check_run", "completed":
                request = CheckRunCompleted(**request_dict)
                _, g = get_github_client(request.installation.id)
                repo = g.get_repo(request.repository.full_name)
                pull_requests = request.check_run.pull_requests
                if pull_requests:
                    logger.info(pull_requests[0].number)
                    pr = repo.get_pull(pull_requests[0].number)
                    if (time.time() - pr.created_at.timestamp()) > 60 * 60 and (
                        pr.title.startswith("[Sweep Rules]")
                        or pr.title.startswith("[Sweep GHA Fix]")
                    ):
                        after_sha = pr.head.sha
                        commit = repo.get_commit(after_sha)
                        check_suites = commit.get_check_suites()
                        for check_suite in check_suites:
                            if check_suite.conclusion == "failure":
                                pr.edit(state="closed")
                                break
                    if (
                        not (time.time() - pr.created_at.timestamp()) > 60 * 15
                        and request.check_run.conclusion == "failure"
                        and pr.state == "open"
                        and get_gha_enabled(repo)
                        and len(
                            [
                                comment
                                for comment in pr.get_issue_comments()
                                if "Fixing PR" in comment.body
                            ]
                        )
                        < 2
                        and GHA_AUTOFIX_ENABLED
                    ):
                        # check if the base branch is passing
                        commits = repo.get_commits(sha=pr.base.ref)
                        latest_commit: Commit = commits[0]
                        if all(
                            status != "failure"
                            for status in [
                                status.state for status in latest_commit.get_statuses()
                            ]
                        ):  # base branch is passing
                            logs = download_logs(
                                request.repository.full_name,
                                request.check_run.run_id,
                                request.installation.id,
                            )
                            logs, user_message = clean_gh_logs(logs)
                            attributor = request.sender.login
                            if attributor.endswith("[bot]"):
                                attributor = commit.author.login
                            if attributor.endswith("[bot]"):
                                attributor = pr.assignee.login
                            if attributor.endswith("[bot]"):
                                return {
                                    "success": False,
                                    "error_message": "The PR was created by a bot, so I won't attempt to fix it.",
                                }
                            chat_logger = ChatLogger(
                                data={
                                    "username": attributor,
                                    "title": "[Sweep GHA Fix] Fix the failing GitHub Actions",
                                }
                            )
                            if chat_logger.use_faster_model() and not IS_SELF_HOSTED:
                                return {
                                    "success": False,
                                    "error_message": "Disabled for free users",
                                }
                            # stack_pr(
                            #     request=f"[Sweep GHA Fix] The GitHub Actions run failed on {request.check_run.head_sha[:7]} ({repo.default_branch}) with the following error logs:\n\n```\n\n{logs}\n\n```",
                            #     pr_number=pr.number,
                            #     username=attributor,
                            #     repo_full_name=repo.full_name,
                            #     installation_id=request.installation.id,
                            #     tracking_id=tracking_id,
                            #     commit_hash=pr.head.sha,
                            # )
            case "pull_request", "opened":
                try:
                    pr_request = PRRequest(**request_dict)
                    _, g = get_github_client(request_dict["installation"]["id"])
                    repo = g.get_repo(request_dict["repository"]["full_name"])
                    pr = repo.get_pull(request_dict["pull_request"]["number"])
                    # check if review_pr is restricted
                    allowed_repos = os.environ.get("PR_REVIEW_REPOS", "")
                    allowed_repos_set = set(allowed_repos.split(',')) if allowed_repos else set()
                    allowed_usernames = os.environ.get("PR_REVIEW_USERNAMES", "")
                    allowed_usernames_set = set(allowed_usernames.split(',')) if allowed_usernames else set()
                    # only call review pr if user names are allowed
                    # defaults to all users/repos if not set
                    if (not allowed_repos or repo.name in allowed_repos_set) and (not allowed_usernames or pr.user.login in allowed_usernames_set):
                        # run pr review
                        call_review_pr(
                            username=pr.user.login,
                            pr=pr,
                            repository=repo,
                            installation_id=pr_request.installation.id,
                            pr_labelled=False,
                        )
                except Exception as e:
                    logger.exception(f"Failed to review PR: {e}")
                    raise e
            case "pull_request", "labeled":
                try:
                    pr_request = PRLabeledRequest(**request_dict)
                    # run only if sweep label is added to the pull request
                    if (
                        GITHUB_LABEL_NAME in [label.name.lower() for label in pr_request.pull_request.labels] 
                    ):
                        _, g = get_github_client(request_dict["installation"]["id"])
                        repo = g.get_repo(request_dict["repository"]["full_name"])
                        pr = repo.get_pull(request_dict["pull_request"]["number"])

                        # run pr review - no need to check for allowed users/repos if they are adding sweep label
                        call_review_pr(
                            username=pr.user.login,
                            pr=pr,
                            repository=repo,
                            installation_id=pr_request.installation.id,
                            pr_labelled=True,
                        )
                    else:
                        logger.info("sweep label not in pull request labels")

                except Exception as e:
                    logger.exception(f"Failed to review PR: {e}")
                    raise e
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
                        try:
                            repo.create_label(
                                name=GITHUB_LABEL_NAME,
                                color=GITHUB_LABEL_COLOR,
                                description=GITHUB_LABEL_DESCRIPTION,
                            )
                        except GithubException as e:
                            if e.status == 422 and any(error.get("code") == "already_exists" for error in e.data.get("errors", [])):
                                logger.warning(f"Label '{GITHUB_LABEL_NAME}' already exists in the repository")
                            else:
                                raise e
                    current_issue = repo.get_issue(number=request.issue.number)
                    current_issue.add_to_labels(GITHUB_LABEL_NAME)
            case "issue_comment", "edited":
                request = IssueCommentRequest(**request_dict)
                sweep_labeled_issue = GITHUB_LABEL_NAME in [
                    label.name.lower() for label in request.issue.labels
                ]
                button_title_match = check_button_title_match(
                    REVERT_CHANGED_FILES_TITLE,
                    request.comment.body,
                    request.changes,
                ) or check_button_title_match(
                    RULES_TITLE,
                    request.comment.body,
                    request.changes,
                )
                if (
                    request.comment.user.type == "Bot"
                    and GITHUB_BOT_USERNAME in request.comment.user.login
                    and request.changes.body_from is not None
                    and button_title_match
                    and request.sender.type == "User"
                    and request.comment.user.login not in BLACKLISTED_USERS
                ):
                    run_on_button_click(request_dict)

                restart_sweep = False
                if (
                    request.comment.user.type == "Bot"
                    and GITHUB_BOT_USERNAME in request.comment.user.login
                    and request.changes.body_from is not None
                    and check_button_activated(
                        RESTART_SWEEP_BUTTON,
                        request.comment.body,
                        request.changes,
                    )
                    and sweep_labeled_issue
                    and request.sender.type == "User"
                    and request.comment.user.login not in BLACKLISTED_USERS
                ):
                    # Restart Sweep on this issue
                    restart_sweep = True

                if (
                    request.issue is not None
                    and sweep_labeled_issue
                    and request.comment.user.type == "User"
                    and request.comment.user.login not in BLACKLISTED_USERS
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
                    request.issue.pull_request
                    and request.comment.user.type == "User"
                    and request.comment.user.login not in BLACKLISTED_USERS
                ):
                    if should_handle_comment(request):
                        logger.info(f"Handling comment on PR: {request.issue.pull_request}")
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
            case "issues", "edited":
                request = IssueRequest(**request_dict)
                if (
                    GITHUB_LABEL_NAME
                    in [label.name.lower() for label in request.issue.labels]  
                    and request.sender.type == "User"
                    and not request.sender.login.startswith("sweep")
                ):
                    logger.info("New issue edited")
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
                if (
                    any(
                        label.name.lower() == GITHUB_LABEL_NAME
                        for label in request.issue.labels
                    )
                    and not request.issue.pull_request
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
                    and request.comment.user.login not in BLACKLISTED_USERS
                    and not (
                        request.issue.pull_request and request.issue.pull_request.url
                    )
                    and BOT_SUFFIX not in request.comment.body
                ):
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
                    request.issue.pull_request
                    and request.comment.user.type == "User"
                    and request.comment.user.login not in BLACKLISTED_USERS
                    and BOT_SUFFIX not in request.comment.body
                ):
                    if should_handle_comment(request):
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
                request = CommentCreatedRequest(**request_dict)
                if should_handle_comment(request):
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
            case "pull_request_review_comment", "edited":
                request = CommentCreatedRequest(**request_dict)
                if should_handle_comment(request):
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
            case "installation_repositories", "added":
                # don't do anything for now
                pass
            case "installation", "created":
                # don't do anything for now
                pass
            case "pull_request", "edited":
                request = PREdited(**request_dict)

                if (
                    request.pull_request.user.login == GITHUB_BOT_USERNAME
                    and not request.sender.login.endswith("[bot]")
                ):
                    try:
                        _, g = get_github_client(request.installation.id)
                        repo = g.get_repo(request.repository.full_name)
                        pr = repo.get_pull(request.pull_request.number)
                        # check if review_pr is restricted
                        allowed_repos = os.environ.get("PR_REVIEW_REPOS", "")
                        allowed_repos_set = set(allowed_repos.split(',')) if allowed_repos else set()
                        if not allowed_repos or repo.name in allowed_repos_set:
                            # run pr review
                            call_review_pr(
                                username=pr.user.login,
                                pr=pr,
                                repository=repo,
                                installation_id=request.installation.id,
                            )
                    except Exception as e:
                        logger.exception(f"Failed to review PR: {e}")
                        raise e
            case "pull_request", "closed":
                pr_request = PRRequest(**request_dict)
                (
                    organization,
                    repo_name,
                ) = pr_request.repository.full_name.split("/")
                commit_author = pr_request.pull_request.user.login
                merged_by = (
                    pr_request.pull_request.merged_by.login
                    if pr_request.pull_request.merged_by
                    else None
                )
                if CURRENT_USERNAME == commit_author and merged_by is not None:
                    event_name = "merged_sweep_pr"
                    if pr_request.pull_request.title.startswith("[config]"):
                        event_name = "config_pr_merged"
                    elif pr_request.pull_request.title.startswith("[Sweep Rules]"):
                        event_name = "sweep_rules_pr_merged"
                    edited_by_developers = False
                    _token, g = get_github_client(pr_request.installation.id)
                    pr = g.get_repo(pr_request.repository.full_name).get_pull(
                        pr_request.number
                    )
                    
                    total_lines_in_commit = 0
                    total_lines_edited_by_developer = 0
                    edited_by_developers = False
                    for commit in pr.get_commits():
                        lines_modified = commit.stats.additions + commit.stats.deletions
                        total_lines_in_commit += lines_modified
                        if commit.author.login != CURRENT_USERNAME:
                            total_lines_edited_by_developer += lines_modified
                    # this was edited by a developer if at least 25% of the lines were edited by a developer
                    edited_by_developers = total_lines_in_commit > 0 and (total_lines_edited_by_developer / total_lines_in_commit) >= 0.25
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
                            "edited_by_developers": edited_by_developers,
                            "total_lines_in_commit": total_lines_in_commit,
                            "total_lines_edited_by_developer": total_lines_edited_by_developer,
                        },
                    )
                chat_logger = ChatLogger({"username": merged_by})
            case "ping", None:
                return {"message": "pong"}
            case _:
                return {"error": "Unsupported type"}
