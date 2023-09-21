from typing import List

from sweepai.events import IssueCommentChanges


import html

def create_button(label: str, selected: bool = False):
    escaped_label = html.escape(label)
    return f"- [{'x' if selected else ' '}] {escaped_label}"


def create_action_buttons(labels: List[str]):
    header = "## Actions (click)\n"
    buttons = "\n".join(create_button(label) for label in labels)
    return header + buttons


import html

def get_toggled_state(label: str, changes_request: IssueCommentChanges) -> bool:
    old_content = changes_request.changes.body["from"]
    escaped_label = html.escape(label)
    button = create_button(escaped_label, selected=True)
    return button.lower() in old_content.lower()


import html

def check_button_activated(
    label: str, body: str, changes_request: IssueCommentChanges | None = None
) -> bool:
    if changes_request:
        escaped_label = html.escape(label)
        if get_toggled_state(escaped_label, changes_request):
            # If the issue was previously activated, do not activate it again
            return False

    escaped_label = html.escape(label)
    button = create_button(escaped_label, selected=True)
    return button.lower() in body.lower()
