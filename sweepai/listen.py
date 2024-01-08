import asyncio
import datetime
import os
import time

from github import Github
from github.Repository import Repository

from sweepai.api import handle_request


def stream_events(repo: Repository, timeout: int = 3, offset: int = 60 * 60):
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
    print(event)
    asyncio.run(handle_request(event.payload))
