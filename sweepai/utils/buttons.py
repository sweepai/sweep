from typing import List

from sweepai.events import IssueCommentChanges, Changes


def create_button(label: str, selected: bool = False) -> str:
    """Create a button for the issue body."""
    return f"- [{'x' if selected else ' '}] {label}"


def create_revert_buttons(file_list: List[str], header="## Revert Actions (click)\n") -> List[str]:
    """Create a list of revert buttons for each file in the pull request."""
    revert_buttons = [create_button(f"Revert {file}") for file in file_list]
    return header + "\n".join(revert_buttons)


def get_toggled_state(label: str, changes_request: Changes) -> bool:
    """Get the toggled state of a button."""
    old_content = changes_request.body_from
    button = create_button(label, selected=True)
    return button.lower() in old_content.lower()


def check_button_activated(
    label: str, body: str, changes_request: Changes | None = None
) -> bool:
    """Check if a button is activated based on its current and past state."""
    if changes_request:
        if get_toggled_state(label, changes_request):
            # If the issue was previously activated, do not activate it again
            return False

    button = create_button(label, selected=True)
    return button.lower() in body.lower()
