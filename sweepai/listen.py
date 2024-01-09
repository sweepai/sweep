import asyncio
import datetime
import os
import time

from github import Github
from github.Event import Event
from github.Repository import Repository

from sweepai.api import handle_request


def pascal_to_snake(name):
    return "".join(["_" + i.lower() if i.isupper() else i for i in name]).lstrip("_")


def get_event_type(event: Event):
    return pascal_to_snake(event.type)[: -len("_event")]


def stream_events(repo: Repository, timeout: int = 3, offset: int = 5 * 60):
    processed_event_ids = set()
    events = repo.get_events()

    current_time = time.time() - offset
    local_tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo

    while True:
        events = repo.get_events()
        for event in list(events)[::-1]:
            if event.id not in processed_event_ids:
                local_time = event.created_at.replace(
                    tzinfo=datetime.timezone.utc
                ).astimezone(local_tz)

                if local_time.timestamp() > current_time:
                    yield event
            processed_event_ids.add(event.id)
        time.sleep(timeout)


g = Github(os.environ["GITHUB_PAT"])
repo = g.get_repo(os.environ["REPO"])
print("Starting server, listening to events...")
for event in stream_events(repo):
    payload = {**event.raw_data, **event.payload}
    payload["sender"] = payload.get("sender", payload["actor"])
    payload["sender"]["type"] = "User"
    payload["pusher"] = payload.get("pusher", payload["actor"])
    payload["pusher"]["name"] = payload["pusher"]["login"]
    payload["pusher"]["type"] = "User"
    payload["after"] = payload.get("after", payload.get("head"))
    payload["repository"] = event.repo.raw_data
    payload["installation"] = {"id": -1}
    print(event.created_at)
    asyncio.run(handle_request(payload, get_event_type(event)))
