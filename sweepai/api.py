# Do not save logs for main process
import json

from logn import logger
from github import PullRequest, InputGitTreeElement
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
    IssueCommentChanges,
    PREdited,
)
from sweepai.handlers.create_pr import create_gha_pr, add_config_to_top_repos  # type: ignore
from sweepai.handlers.create_pr import create_pr_changes, safe_delete_sweep_branch
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


# New function to create a revert button for each file in a pull request
def create_revert_button(file_path: str) -> str:
    return f"[ ] Revert {file_path}"

# New function to handle the action when a revert button is activated
def handle_revert_button_activation(pull_request: PullRequest, file_path: str):
    _, g = get_github_client(pull_request.installation.id)
    repo = g.get_repo(pull_request.repository.full_name)
    pr = repo.get_pull(pull_request.number)
    file_commit = next(file for file in pr.get_files() if file.filename == file_path).sha
    base_tree = repo.get_git_tree(repo.default_branch)
    new_tree = repo.create_git_tree([InputGitTreeElement(file_path, "100644", "blob", file_commit)], base_tree)
    parent_commit = repo.get_git_commit(repo.default_branch)
    commit_message = f"Revert changes in {file_path}"
    new_commit = repo.create_git_commit(commit_message, new_tree, [parent_commit])
    repo.create_git_ref(f"refs/heads/revert_changes_in_{file_path}", new_commit.sha)


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
