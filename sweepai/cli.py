import datetime
import os
import pickle
import threading
import time
from itertools import chain, islice

import typer
from github import Github
from github.Event import Event
from github.IssueEvent import IssueEvent
from github.Repository import Repository
from loguru import logger
from rich.console import Console

from sweepai.api import handle_request
from sweepai.handlers.on_ticket import on_ticket
from sweepai.utils.github_utils import get_github_client
from sweepai.utils.str_utils import get_hash
from sweepai.web.events import Account, Installation, IssueRequest

app = typer.Typer()

console = Console()
cprint = console.print


def fetch_issue_request(issue_url: str, __version__: str = "0"):
    (
        protocol_name,
        _,
        _base_url,
        org_name,
        repo_name,
        _issues,
        issue_number,
    ) = issue_url.split("/")
    cprint("Fetching installation ID...")
    installation_id = -1
    cprint("Fetching access token...")
    _token, g = get_github_client(installation_id)
    g: Github = g
    cprint("Fetching repo...")
    issue = g.get_repo(f"{org_name}/{repo_name}").get_issue(int(issue_number))

    issue_request = IssueRequest(
        action="labeled",
        issue=IssueRequest.Issue(
            title=issue.title,
            number=int(issue_number),
            html_url=issue_url,
            user=IssueRequest.Issue.User(
                login=issue.user.login,
                type="User",
            ),
            body=issue.body,
            labels=[
                IssueRequest.Issue.Label(
                    name="sweep",
                ),
            ],
            assignees=None,
            pull_request=None,
        ),
        repository=IssueRequest.Issue.Repository(
            full_name=issue.repository.full_name,
            description=issue.repository.description,
        ),
        assignee=IssueRequest.Issue.Assignee(login=issue.user.login),
        installation=Installation(
            id=installation_id,
            account=Account(
                id=issue.user.id,
                login=issue.user.login,
                type="User",
            ),
        ),
        sender=IssueRequest.Issue.User(
            login=issue.user.login,
            type="User",
        ),
    )
    return issue_request


def pascal_to_snake(name):
    return "".join(["_" + i.lower() if i.isupper() else i for i in name]).lstrip("_")


def get_event_type(event: Event | IssueEvent):
    if isinstance(event, IssueEvent):
        return "issues"
    else:
        return pascal_to_snake(event.type)[: -len("_event")]


@app.command()
def watch(
    repo_name: str,
    debug: bool = False,
    record_events: bool = False,
    max_events: int = 30,
):
    GITHUB_PAT = os.environ.get("GITHUB_PAT", None)
    if GITHUB_PAT is None:
        raise ValueError("GITHUB_PAT environment variable must be set")
    g = Github(os.environ["GITHUB_PAT"])
    repo = g.get_repo(repo_name)
    if debug:
        logger.debug("Debug mode enabled")

    def stream_events(repo: Repository, timeout: int = 2, offset: int = 2 * 60):
        processed_event_ids = set()
        current_time = time.time() - offset
        current_time = datetime.datetime.fromtimestamp(current_time)
        local_tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo

        while True:
            events_iterator = chain(
                islice(repo.get_events(), max_events),
                islice(repo.get_issues_events(), max_events),
            )
            for i, event in enumerate(events_iterator):
                if event.id not in processed_event_ids:
                    local_time = event.created_at.replace(
                        tzinfo=datetime.timezone.utc
                    ).astimezone(local_tz)

                    if local_time.timestamp() > current_time.timestamp():
                        yield event
                    else:
                        if debug:
                            logger.debug(
                                f"Skipping event {event.id} because it is in the past (local_time={local_time}, current_time={current_time}, i={i})"
                            )
                if debug:
                    logger.debug(
                        f"Skipping event {event.id} because it is already handled"
                    )
                processed_event_ids.add(event.id)
            time.sleep(timeout)

    def handle_event(event: Event | IssueEvent, do_async: bool = True):
        if isinstance(event, IssueEvent):
            payload = event.raw_data
            payload["action"] = payload["event"]
        else:
            payload = {**event.raw_data, **event.payload}
        payload["sender"] = payload.get("sender", payload["actor"])
        payload["sender"]["type"] = "User"
        payload["pusher"] = payload.get("pusher", payload["actor"])
        payload["pusher"]["name"] = payload["pusher"]["login"]
        payload["pusher"]["type"] = "User"
        payload["after"] = payload.get("after", payload.get("head"))
        payload["repository"] = repo.raw_data
        payload["installation"] = {"id": -1}
        logger.info(str(event) + " " + str(event.created_at))
        if record_events:
            _type = get_event_type(event) if isinstance(event, Event) else "issue"
            pickle.dump(
                event,
                open(
                    "tests/events/"
                    + f"{_type}_{payload.get('action')}_{str(event.id)}.pkl",
                    "wb",
                ),
            )
        if do_async:
            thread = threading.Thread(
                target=handle_request, args=(payload, get_event_type(event))
            )
            thread.start()
            return thread
        else:
            return handle_request(payload, get_event_type(event))

    def main():
        cprint(
            f"\n[bold black on white]  Starting server, listening to events from {repo_name}...  [/bold black on white]\n",
        )
        cprint(
            f"To create a PR, please create an issue at https://github.com/{repo_name}/issues with a title prefixed with 'Sweep:' or label an existing issue with 'sweep'. The events will be logged here, but there may be a brief delay.\n"
        )
        for event in stream_events(repo):
            handle_event(event)

    if __name__ == "__main__":
        main()


@app.command()
def run(issue_url: str):
    cprint(f"\n  Running Sweep on issue: {issue_url}  \n", style="bold black on white")

    request = fetch_issue_request(issue_url)

    cprint(f'\nRunning Sweep to solve "{request.issue.title}"!\n')
    on_ticket(
        title=request.issue.title,
        summary=request.issue.body,
        issue_number=request.issue.number,
        issue_url=request.issue.html_url,
        username=request.sender.login,
        repo_full_name=request.repository.full_name,
        repo_description=request.repository.description,
        installation_id=request.installation.id,
        comment_id=None,
        edited=False,
        tracking_id=get_hash(),
    )


if __name__ == "__main__":
    app()
