import re
from jira import JIRA

from sweepai.handlers.on_ticket import on_ticket
from sweepai.utils.github_utils import get_github_client, get_installation_id
from sweepai.config.server import JIRA_API_TOKEN, JIRA_URL, JIRA_USER_NAME

def extract_repo_name_from_description(description):
    repo_full_name = None
    pattern = r'repo:\s*(\S+/\S+)'
    match = re.search(pattern, description)
    if match:
        repo_full_name = match.group(1)
    return repo_full_name


def comment_on_jira_webhook(webhook_data: dict, comment_text: str):
    # Extract relevant information from the webhook payload
    issue_key = webhook_data['issue']['key']

    # Create a JIRA client instance
    jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_USER_NAME, JIRA_API_TOKEN))

    # Add the comment to the Jira issue
    jira.add_comment(issue_key, comment_text)

def handle_jira_ticket(event):
    # Do something with the JIRA ticket
    jira_issue = event["issue"]
    # get title, description, comments
    title = jira_issue["fields"]["summary"]
    description = jira_issue["fields"]["description"]
    # comments = issue["fields"]["comment"]["comments"]
    # parse github repo from description
    # ex: "repo: sweepai/sweep"
    repo_full_name = extract_repo_name_from_description(description)
    if not repo_full_name:
        return
    repo_full_name = repo_full_name.strip()
    org_name, _ = repo_full_name.split("/")
    # create a github issue to sync the data

    installation_id = get_installation_id(org_name)
    _, g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    github_issue = repo.create_issue(title=title, body=description)
    
    # wait for this
    on_ticket(
        username=github_issue.user.login,
        title=title,
        summary=description,
        issue_number=github_issue.number,
        issue_url=github_issue.html_url,
        repo_full_name=repo_full_name,
        repo_description=repo.description,
        installation_id=installation_id,
        comment_id=None,
        edited=False,
        tracking_id=None,
    )
    # refresh credentials to get attached pr and then comment this back on the JIRA ticket
    # refresh github credentials
    _, g = get_github_client(installation_id)
    repo = g.get_repo(repo_full_name)
    github_issue = repo.get_issue(github_issue.number)
    # get the PR by iterating through the latest issues
    prs = repo.get_pulls(
        state="open",
        sort="created",
        direction="desc",
    )
    resolution_pr = None
    for pr in prs.get_page(0):
        # # Check if this issue is mentioned in the PR, and pr is owned by bot
        # # This is done in create_pr, (pr_description = ...)
        if f"Fixes #{github_issue.number}.\n" in pr.body:
            resolution_pr = pr
            break
    if not resolution_pr:
        comment_text = "I have created a corresponding GitHub Issue:\n {github_issue.html_url}"
    else:
        comment_text = f"I have created a corresponding GitHub Issue and GitHub PR:\n{github_issue.html_url}\n{resolution_pr.html_url}"
    comment_on_jira_webhook(webhook_data=event, comment_text=comment_text)


