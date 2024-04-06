

from sweepai.handlers.on_ticket import on_ticket
from sweepai.web.event_utils import fetch_issue_request


def handle_jira_ticket(event):
    # Do something with the JIRA ticket
    breakpoint()
    issue = event["issue"]
    # get title, description, comments
    title = issue["fields"]["summary"]
    description = issue["fields"]["description"]
    comments = issue["fields"]["comment"]["comments"]
    # parse github repo from description
    # ex: "repo: sweepai/sweep"
    repo_full_name = None
    for line in description.split("\n"):
        if line.startswith("repo: "):
            repo_full_name = line.split("repo: ")[1]
            break
    if not repo_full_name:
        return
    repo_full_name = repo_full_name.strip()
    org_name, repo_name = repo_full_name.split("/")

    return on_ticket(
        title=title,
        summary=description,
    )
