from typing import List
from github import PullRequest

from sweepai.events import IssueCommentChanges, Changes


def create_button(label: str, selected: bool = False) -> str:
    """Create a button for the issue body."""
    return f"- [{'x' if selected else ' '}] {label}"


def create_action_buttons(labels: List[str], header="## Actions (click)\n") -> str:
    """Create a list of buttons for the issue body."""
    buttons = "\n".join(create_button(label) for label in labels)
    return header + buttons


def get_toggled_state(label: str, changes_request: Changes) -> bool:
    """Get the toggled state of a button."""
    old_content = changes_request.body_from
    button = create_button(label, selected=True)
    return button.lower() in old_content.lower()


def create_revert_button(file_path: str) -> str:
    """Create a revert button for a file."""
    return f"[ ] Revert {file_path}"

def check_button_activated(
    label: str, body: str, changes_request: Changes | None = None
) -> bool:
    """Check if a button is activated based on its current and past state."""
    if changes_request:
        if get_toggled_state(label, changes_request):
            # If the issue was previously activated, do not activate it again
            return False

    if label.startswith("[ ] Revert"):
        file_path = label.split(" ")[2]
        if file_path in changes_request.files:
            button = create_revert_button(file_path)
            return button.lower() in body.lower()

    button = create_button(label, selected=True)
    return button.lower() in body.lower()

def handle_revert_button_activation(pull_request: PullRequest, file_path: str):
    """Handle the action when a revert button is activated."""
    # Use the GitHub API to revert the changes made to the file in the pull request
    commit = pull_request.head.sha
    pull_request.repo.revert(commit, file_path)
