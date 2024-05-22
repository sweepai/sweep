import datetime
import json
import os
import pickle
import threading
import time
import uuid
from itertools import chain, islice

import typer
from github import Github
from github.Event import Event
from github.IssueEvent import IssueEvent
from github.Repository import Repository
from loguru import logger
from rich.console import Console
from rich.prompt import Prompt

from sweepai.api import handle_request
from sweepai.handlers.on_ticket import on_ticket
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import get_github_client
from sweepai.utils.str_utils import get_hash
from sweepai.web.events import Account, Installation, IssueRequest

app = typer.Typer(
    name="sweepai", context_settings={"help_option_names": ["-h", "--help"]}
)
app_dir = typer.get_app_dir("sweepai")
config_path = os.path.join(app_dir, "config.json")
os.environ["CLI"] = "True"

console = Console()
cprint = console.print


def posthog_capture(event_name, properties, *args, **kwargs):
    POSTHOG_DISTINCT_ID = os.environ.get("POSTHOG_DISTINCT_ID")
    if POSTHOG_DISTINCT_ID:
        posthog.capture(POSTHOG_DISTINCT_ID, event_name, properties, *args, **kwargs)


def load_config():
    if os.path.exists(config_path):
        cprint(f"\nLoading configuration from {config_path}", style="yellow")
        with open(config_path, "r") as f:
            config = json.load(f)
        for key, value in config.items():
            try:
                os.environ[key] = value
            except Exception as e:
                cprint(f"Error loading config: {e}, skipping.", style="yellow")
        os.environ["POSTHOG_DISTINCT_ID"] = str(os.environ.get("POSTHOG_DISTINCT_ID", ""))
        # Should contain:
        # GITHUB_PAT
        # OPENAI_API_KEY
        # ANTHROPIC_API_KEY
        # VOYAGE_API_KEY
        # POSTHOG_DISTINCT_ID


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
def test():
    cprint("Sweep AI is installed correctly and ready to go!", style="yellow")

@app.command()
def watch(
    repo_name: str,
    debug: bool = False,
    record_events: bool = False,
    max_events: int = 30,
):
    if not os.path.exists(config_path):
        cprint(
            f"\nConfiguration not found at {config_path}. Please run [green]'sweep init'[/green] to initialize the CLI.\n",
            style="yellow",
        )
        raise ValueError(
            "Configuration not found, please run 'sweep init' to initialize the CLI."
        )
    posthog_capture(
        "sweep_watch_started",
        {
            "repo": repo_name,
            "debug": debug,
            "record_events": record_events,
            "max_events": max_events,
        },
    )
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
def init(override: bool = False):
    # TODO: Fix telemetry
    if not override:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
                if "OPENAI_API_KEY" in config and "ANTHROPIC_API_KEY" in config and "GITHUB_PAT" in config:
                    override = typer.confirm(
                        f"\nConfiguration already exists at {config_path}. Override?",
                        default=False,
                        abort=True,
                    )
    cprint(
        "\n[bold black on white]  Initializing Sweep CLI...  [/bold black on white]\n",
    )
    cprint(
        "\nFirstly, let's store your OpenAI API Key. You can get it here: https://platform.openai.com/api-keys\n",
        style="yellow",
    )
    openai_api_key = Prompt.ask("OpenAI API Key", password=True)
    assert len(openai_api_key) > 30, "OpenAI API Key must be of length at least 30."
    assert openai_api_key.startswith("sk-"), "OpenAI API Key must start with 'sk-'."
    cprint(
        "\nNext, let's store your Anthropic API key. You can get it here: https://console.anthropic.com/settings/keys.",
        style="yellow",
    )
    anthropic_api_key = Prompt.ask("Anthropic API Key", password=True)
    assert len(anthropic_api_key) > 30, "Anthropic API Key must be of length at least 30."
    assert anthropic_api_key.startswith("sk-ant-api03-"), "GitHub PAT must start with 'ghp_'."
    cprint(
        "\nGreat! Next, we'll need just your GitHub PAT. Here's a link with all the permissions pre-filled:\nhttps://github.com/settings/tokens/new?description=Sweep%20Self-hosted&scopes=repo,workflow\n",
        style="yellow",
    )
    github_pat = Prompt.ask("GitHub PAT", password=True)
    assert len(github_pat) > 30, "GitHub PAT must be of length at least 30."
    assert github_pat.startswith("ghp_"), "GitHub PAT must start with 'ghp_'."
    cprint(
        "\nAwesome! Lastly, let's get your Voyage AI API key from https://dash.voyageai.com/api-keys. This is optional, but improves code search by about [cyan]3%[/cyan]. You can always return to this later by re-running 'sweep init'.",
        style="yellow",
    )
    voyage_api_key = Prompt.ask("Voyage AI API key", password=True)
    if voyage_api_key:
        assert len(voyage_api_key) > 30, "Voyage AI API key must be of length at least 30."
        assert voyage_api_key.startswith("pa-"), "Voyage API key must start with 'pa-'."

    POSTHOG_DISTINCT_ID = None
    enable_telemetry = typer.confirm(
        "\nEnable usage statistics? This will help us improve the product.",
        default=True,
    )
    if enable_telemetry:
        cprint(
            "\nThank you for enabling telemetry. We'll collect anonymous usage statistics to improve the product. You can disable this at any time by rerunning 'sweep init'.",
            style="yellow",
        )
        POSTHOG_DISTINCT_ID = str(uuid.getnode())
        posthog.capture(POSTHOG_DISTINCT_ID, "sweep_init", {})

    config = {
        "GITHUB_PAT": github_pat,
        "OPENAI_API_KEY": openai_api_key,
        "ANTHROPIC_API_KEY": anthropic_api_key,
        "VOYAGE_API_KEY": voyage_api_key,
    }
    if POSTHOG_DISTINCT_ID:
        config["POSTHOG_DISTINCT_ID"] = POSTHOG_DISTINCT_ID
    os.makedirs(app_dir, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f)

    cprint(f"\nConfiguration saved to {config_path}\n", style="yellow")

    cprint(
        "Installation complete! You can now run [green]'sweep run <issue-url>'[/green][yellow] to run Sweep on an issue. or [/yellow][green]'sweep watch <org-name>/<repo-name>'[/green] to have Sweep listen for and fix newly created GitHub issues.",
        style="yellow",
    )


@app.command()
def run(issue_url: str):
    if not os.path.exists(config_path):
        cprint(
            f"\nConfiguration not found at {config_path}. Please run [green]'sweep init'[/green] to initialize the CLI.\n",
            style="yellow",
        )
        raise ValueError(
            "Configuration not found, please run 'sweep init' to initialize the CLI."
        )

    cprint(f"\n  Running Sweep on issue: {issue_url}  \n", style="bold black on white")

    posthog_capture("sweep_run_started", {"issue_url": issue_url})

    request = fetch_issue_request(issue_url)

    try:
        cprint(f'\nRunning Sweep to solve "{request.issue.title}"!\n')
        on_ticket(
            username=request.sender.login,
            title=request.issue.title,
            summary=request.issue.body,
            issue_number=request.issue.number,
            issue_url=request.issue.html_url,
            repo_full_name=request.repository.full_name,
            repo_description=request.repository.description,
            installation_id=request.installation.id,
            comment_id=None,
            edited=False,
            tracking_id=get_hash(),
        )
    except Exception as e:
        posthog_capture("sweep_run_fail", {"issue_url": issue_url, "error": str(e)})
    else:
        posthog_capture("sweep_run_success", {"issue_url": issue_url})


def main():
    cprint(
        "By using the Sweep CLI, you agree to the Sweep AI Terms of Service at https://sweep.dev/tos.pdf",
        style="cyan",
    )
    load_config()
    app()


if __name__ == "__main__":
    main()
