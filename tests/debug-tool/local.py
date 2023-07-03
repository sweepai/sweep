# Use this script to run Sweep locally

# Load secrets
from test_secrets import load_secrets
load_secrets()

from sweepai.utils.github_utils import get_github_client, get_installation_id

organization_name, repo_full_name = "sweepai", "sweepai/sweep"
installation_id = get_installation_id(organization_name)
g = get_github_client(installation_id)
repo = g.get_repo(repo_full_name)
print(repo)

from sweepai.handlers.on_ticket import on_ticket

on_ticket(
    "Sweep: write unit tests",
    "Description",
    166,
    "issue url",
    "lucasjagg",
    repo_full_name,
    "Sweep",
    installation_id,
)