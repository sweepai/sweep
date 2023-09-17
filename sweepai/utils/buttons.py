from typing import List

from sweepai.events import IssueCommentChanges


def create_button(label: str, selected: bool = False):
    return f"- [{'x' if selected else ' '}] {label}"


def create_action_buttons(labels: List[str]):
    header = "## Actions (click)\n"
    buttons = "\n".join(create_button(label) for label in labels)
    return header + buttons


def get_toggled_state(label: str, changes_request: IssueCommentChanges) -> bool:
    old_content = changes_request.changes.body["from"]
    button = create_button(label, selected=True)
    return button.lower() in old_content.lower()


def check_button_activated(
    label: str, body: str, changes_request: IssueCommentChanges | None = None
) -> bool:
    if changes_request:
        if get_toggled_state(label, changes_request):
            # If the issue was previously activated, do not activate it again
            return False

    button = create_button(label, selected=True)
    return button.lower() in body.lower()
