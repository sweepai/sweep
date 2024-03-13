from __future__ import annotations

# Do not save logs for main process
import ctypes
import json
import subprocess
import threading
import time
from typing import Any, Optional

import requests
from fastapi import (
    Body,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Request,
    Security,
    status,
)
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.templating import Jinja2Templates
from github.Commit import Commit
from prometheus_fastapi_instrumentator import Instrumentator

from sweepai.config.client import (
    DEFAULT_RULES,
    RESTART_SWEEP_BUTTON,
    REVERT_CHANGED_FILES_TITLE,
    RULES_LABEL,
    RULES_TITLE,
    SWEEP_BAD_FEEDBACK,
    SWEEP_GOOD_FEEDBACK,
    SweepConfig,
    get_gha_enabled,
    get_rules,
)
from sweepai.config.server import (
    DISABLED_REPOS,
    DISCORD_FEEDBACK_WEBHOOK_URL,
    ENV,
    GHA_AUTOFIX_ENABLED,
    GITHUB_BOT_USERNAME,
    GITHUB_LABEL_COLOR,
    GITHUB_LABEL_DESCRIPTION,
    GITHUB_LABEL_NAME,
    IS_SELF_HOSTED,
    MERGE_CONFLICT_ENABLED,
)
from sweepai.core.entities import PRChangeRequest
from sweepai.global_threads import global_threads
from sweepai.handlers.create_pr import (  # type: ignore
    add_config_to_top_repos,
    create_gha_pr,
)
from sweepai.handlers.on_button_click import handle_button_click
from sweepai.handlers.on_check_suite import (  # type: ignore
    clean_gh_logs,
    download_logs,
    on_check_suite,
)
from sweepai.handlers.on_comment import on_comment
from sweepai.handlers.on_merge import on_merge
from sweepai.handlers.on_merge_conflict import on_merge_conflict
from sweepai.handlers.on_ticket import on_ticket
from sweepai.handlers.pr_utils import make_pr
from sweepai.handlers.stack_pr import stack_pr
from sweepai.utils.buttons import (
    Button,
    ButtonList,
    check_button_activated,
    check_button_title_match,
)
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import logger, posthog
from sweepai.utils.github_utils import CURRENT_USERNAME, get_github_client
from sweepai.utils.progress import TicketProgress
from sweepai.utils.safe_pqueue import SafePriorityQueue
from sweepai.utils.str_utils import BOT_SUFFIX, get_hash
from sweepai.web.events import (
    CheckRunCompleted,
    CommentCreatedRequest,
    InstallationCreatedRequest,
    IssueCommentRequest,
    IssueRequest,
    PREdited,
    PRRequest,
    ReposAddedRequest,
)
from sweepai.web.health import health_check

app = FastAPI()

events = {}
on_ticket_events = {}

security = HTTPBearer()

templates = Jinja2Templates(directory="sweepai/web")
version_command = r"""git config --global --add safe.directory /app
timestamp=$(git log -1 --format="%at")
date -d "@$timestamp" +%y.%m.%d.%H 2>/dev/null || date -r "$timestamp" +%y.%m.%d.%H"""
try:
    version = subprocess.check_output(version_command, shell=True, text=True).strip()
except Exception:
    version = time.strftime("%y.%m.%d.%H")

logger.bind(application="webhook")


def auth_metrics(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication scheme.",
        )
    if credentials.credentials != "example_token":  # grafana requires authentication
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    return True


if not IS_SELF_HOSTED:
    Instrumentator().instrument(app).expose(
        app,
        should_gzip=False,
        endpoint="/metrics",
        include_in_schema=True,
        tags=["metrics"],
        dependencies=[Depends(auth_metrics)],
    )


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


def run_on_button_click(*args, **kwargs):
    thread = threading.Thread(target=handle_button_click, args=args, kwargs=kwargs)
    thread.start()
    global_threads.append(thread)


def run_on_check_suite(*args, **kwargs):
    request = kwargs["request"]
    pr_change_request = on_check_suite(request)
    if pr_change_request:
        call_on_comment(**pr_change_request.params, comment_type="github_action")
        logger.info("Done with on_check_suite")
    else:
        logger.info("Skipping on_check_suite as no pr_change_request was returned")


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

    # delayed_kill_thread = threading.Thread(target=delayed_kill, args=(thread,))
    # delayed_kill_thread.start()


def call_on_check_suite(*args, **kwargs):
    kwargs["request"].repository.full_name
    kwargs["request"].check_run.pull_requests[0].number
    thread = threading.Thread(target=run_on_check_suite, args=args, kwargs=kwargs)
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


def call_on_merge(*args, **kwargs):
    thread = threading.Thread(target=on_merge, args=args, kwargs=kwargs)
    thread.start()
    global_threads.append(thread)


@app.get("/health")
def redirect_to_health():
    return health_check()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        name="index.html", context={"version": version, "request": request}
    )


@app.get("/ticket_progress/{tracking_id}")
def progress(tracking_id: str = Path(...)):
    ticket_progress = TicketProgress.load(tracking_id)
    return ticket_progress.dict()


def init_hatchet() -> Any | None:
    try:
        from hatchet_sdk import Context, Hatchet

        hatchet = Hatchet(debug=True)

        worker = hatchet.worker("github-worker")

        @hatchet.workflow(on_events=["github:webhook"])
        class OnGithubEvent:
            """Workflow for handling GitHub events."""

            @hatchet.step()
            def run(self, context: Context):
                event_payload = context.workflow_input()

                request_dict = event_payload.get("request")
                event = event_payload.get("event")

                run(request_dict, event)

        workflow = OnGithubEvent()
        worker.register_workflow(workflow)

        # start worker in the background
        thread = threading.Thread(target=worker.start)
        thread.start()
        global_threads.append(thread)

        return hatchet
    except Exception as e:
        print(f"Failed to initialize Hatchet: {e}, continuing with local mode")
        return None


# hatchet = init_hatchet()


def handle_github_webhook(event_payload):
    # if hatchet:
    #     hatchet.client.event.push("github:webhook", event_payload)
    # else:
    run(event_payload.get("request"), event_payload.get("event"))


def handle_request(request_dict, event=None):
    """So it can be exported to the listen endpoint."""
    with logger.contextualize(tracking_id="main", env=ENV):
        action = request_dict.get("action")

        try:
            # Send the event to Hatchet
            handle_github_webhook(
                {
                    "request": request_dict,
                    "event": event,
                }
            )
        except Exception as e:
            logger.exception(f"Failed to send event to Hatchet: {e}")

        # try:
        #     worker()
        # except Exception as e:
        #     discord_log_error(str(e), priority=1)
        logger.info(f"Done handling {event}, {action}")
        return {"success": True}


@app.post("/")
def webhook(
    request_dict: dict = Body(...),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
):
    """Handle a webhook request from GitHub."""
    with logger.contextualize(tracking_id="main", env=ENV):
        action = request_dict.get("action", None)
        logger.info(f"Received event: {x_github_event}, {action}")
        return handle_request(request_dict, event=x_github_event)


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


def run(request_dict, event):
    action = request_dict.get("action")

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
                            tracking_id = get_hash()
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
                            stack_pr(
                                request=f"[Sweep GHA Fix] The GitHub Actions run failed on {request.check_run.head_sha[:7]} ({repo.default_branch}) with the following error logs:\n\n```\n\n{logs}\n\n```",
                                pr_number=pr.number,
                                username=attributor,
                                repo_full_name=repo.full_name,
                                installation_id=request.installation.id,
                                tracking_id=tracking_id,
                                commit_hash=pr.head.sha,
                            )
                elif (
                    request.check_run.check_suite.head_branch == repo.default_branch
                    and get_gha_enabled(repo)
                    and GHA_AUTOFIX_ENABLED
                ):
                    if request.check_run.conclusion == "failure":
                        commit = repo.get_commit(request.check_run.head_sha)
                        attributor = request.sender.login
                        if attributor.endswith("[bot]"):
                            attributor = commit.author.login
                        if attributor.endswith("[bot]"):
                            return {
                                "success": False,
                                "error_message": "The PR was created by a bot, so I won't attempt to fix it.",
                            }
                        logs = download_logs(
                            request.repository.full_name,
                            request.check_run.run_id,
                            request.installation.id,
                        )
                        logs, user_message = clean_gh_logs(logs)
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
                        make_pr(
                            title=f"[Sweep GHA Fix] Fix the failing GitHub Actions on {request.check_run.head_sha[:7]} ({repo.default_branch})",
                            repo_description=repo.description,
                            summary=f"The GitHub Actions run failed with the following error logs:\n\n```\n{logs}\n```",
                            repo_full_name=request_dict["repository"]["full_name"],
                            installation_id=request_dict["installation"]["id"],
                            user_token=None,
                            use_faster_model=chat_logger.use_faster_model(),
                            username=attributor,
                            chat_logger=chat_logger,
                        )

            case "pull_request", "opened":
                _, g = get_github_client(request_dict["installation"]["id"])
                repo = g.get_repo(request_dict["repository"]["full_name"])
                pr = repo.get_pull(request_dict["pull_request"]["number"])
                # if the pr already has a comment from sweep bot do nothing
                time.sleep(10)
                if any(
                    comment.user.login == GITHUB_BOT_USERNAME
                    for comment in pr.get_issue_comments()
                ) or pr.title.startswith("Sweep:"):
                    return {
                        "success": True,
                        "reason": "PR already has a comment from sweep bot",
                    }
                rule_buttons = []
                repo_rules = get_rules(repo) or []
                if repo_rules != [""] and repo_rules != []:
                    for rule in repo_rules or []:
                        if rule:
                            rule_buttons.append(Button(label=f"{RULES_LABEL} {rule}"))
                    if len(repo_rules) == 0:
                        for rule in DEFAULT_RULES:
                            rule_buttons.append(Button(label=f"{RULES_LABEL} {rule}"))
                if rule_buttons:
                    rules_buttons_list = ButtonList(
                        buttons=rule_buttons, title=RULES_TITLE
                    )
                    pr.create_issue_comment(rules_buttons_list.serialize() + BOT_SUFFIX)

                if pr.mergeable is False and MERGE_CONFLICT_ENABLED:
                    attributor = pr.user.login
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
                    on_merge_conflict(
                        pr_number=pr.number,
                        username=attributor,
                        repo_full_name=request_dict["repository"]["full_name"],
                        installation_id=request_dict["installation"]["id"],
                        tracking_id=get_hash(),
                    )
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
                ):
                    # Restart Sweep on this issue
                    restart_sweep = True

                if (
                    request.issue is not None
                    and sweep_labeled_issue
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
                    if (
                        comment.lower().startswith("sweep:")
                        or any(label.name.lower() == "sweep" for label in labels)
                    ) and BOT_SUFFIX not in comment:
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
                    and BOT_SUFFIX not in request.comment.body
                ):  # TODO(sweep): set a limit
                    _, g = get_github_client(request.installation.id)
                    repo = g.get_repo(request.repository.full_name)
                    pr = repo.get_pull(request.issue.number)
                    labels = pr.get_labels()
                    comment = request.comment.body
                    if (
                        comment.lower().startswith("sweep:")
                        or any(label.name.lower() == "sweep" for label in labels)
                        and BOT_SUFFIX not in comment
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
                request = CommentCreatedRequest(**request_dict)
                _, g = get_github_client(request.installation.id)
                repo = g.get_repo(request.repository.full_name)
                pr = repo.get_pull(request.pull_request.number)
                labels = pr.get_labels()
                comment = request.comment.body
                if (
                    (
                        comment.lower().startswith("sweep:")
                        or any(label.name.lower() == "sweep" for label in labels)
                    )
                    and request.comment.user.type == "User"
                    and BOT_SUFFIX not in comment
                ):
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
                _, g = get_github_client(request.installation.id)
                repo = g.get_repo(request.repository.full_name)
                pr = repo.get_pull(request.pull_request.number)
                labels = pr.get_labels()
                comment = request.comment.body
                if (
                    (
                        comment.lower().startswith("sweep:")
                        or any(label.name.lower() == "sweep" for label in labels)
                    )
                    and request.comment.user.type == "User"
                    and BOT_SUFFIX not in comment
                ):
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
                    logger.exception(f"Failed to add config to top repos: {e}")

                posthog.capture(
                    "installation_repositories",
                    "started",
                    properties={**metadata},
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
            case "installation", "created":
                repos_added_request = InstallationCreatedRequest(**request_dict)

                try:
                    add_config_to_top_repos(
                        repos_added_request.installation.id,
                        repos_added_request.installation.account.login,
                        repos_added_request.repositories,
                    )
                except Exception as e:
                    logger.exception(f"Failed to add config to top repos: {e}")
            case "pull_request", "edited":
                request = PREdited(**request_dict)

                if (
                    request.pull_request.user.login == GITHUB_BOT_USERNAME
                    and not request.sender.login.endswith("[bot]")
                    and DISCORD_FEEDBACK_WEBHOOK_URL is not None
                ):
                    good_button = check_button_activated(
                        SWEEP_GOOD_FEEDBACK,
                        request.pull_request.body,
                        request.changes,
                    )
                    bad_button = check_button_activated(
                        SWEEP_BAD_FEEDBACK,
                        request.pull_request.body,
                        request.changes,
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
                        requests.post(
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
                            logger.exception(f"Failed to edit PR description: {e}")
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
                    for commit in pr.get_commits():
                        if commit.author.login != CURRENT_USERNAME:
                            edited_by_developers = True
                            break
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
                        },
                    )
                chat_logger = ChatLogger({"username": merged_by})
            case "push", None:
                if event != "pull_request" or request_dict["base"]["merged"] is True:
                    chat_logger = ChatLogger(
                        {"username": request_dict["pusher"]["name"]}
                    )
                    # on merge
                    call_on_merge(request_dict, chat_logger)
                    ref = request_dict["ref"] if "ref" in request_dict else ""
                    if ref.startswith("refs/heads") and not ref.startswith(
                        "ref/heads/sweep"
                    ):
                        _, g = get_github_client(request_dict["installation"]["id"])
                        repo = g.get_repo(request_dict["repository"]["full_name"])
                        if ref[len("refs/heads/") :] == SweepConfig.get_branch(repo):
                            update_sweep_prs_v2(
                                request_dict["repository"]["full_name"],
                                installation_id=request_dict["installation"]["id"],
                            )
                    if ref.startswith("refs/heads"):
                        branch_name = ref[len("refs/heads/") :]
                        # Check if the branch has an associated PR

                        org_name, repo_name = request_dict["repository"][
                            "full_name"
                        ].split("/")
                        pulls = repo.get_pulls(
                            state="open",
                            sort="created",
                            head=org_name + ":" + branch_name,
                        )
                        for pr in pulls:
                            logger.info(
                                f"PR associated with branch {branch_name}: #{pr.number} - {pr.title}"
                            )
                            if pr.mergeable is False and MERGE_CONFLICT_ENABLED:
                                attributor = pr.user.login
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
                                if (
                                    chat_logger.use_faster_model()
                                    and not IS_SELF_HOSTED
                                ):
                                    return {
                                        "success": False,
                                        "error_message": "Disabled for free users",
                                    }
                                on_merge_conflict(
                                    pr_number=pr.number,
                                    username=pr.user.login,
                                    repo_full_name=request_dict["repository"][
                                        "full_name"
                                    ],
                                    installation_id=request_dict["installation"]["id"],
                                    tracking_id=get_hash(),
                                )
            case "ping", None:
                return {"message": "pong"}
            case _:
                return {"error": "Unsupported type"}
