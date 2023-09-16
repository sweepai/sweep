from typing import List

from sweepai.events import IssueCommentChanges


def get_toggled_state(changes_request: IssueCommentChanges) -> bool:
    old_content = changes_request.changes.body["from"]


def create_button(label: str, selected: bool = False):
    return f"- [{'X' if selected else ' '}] {label}"


def create_action_buttons(labels: List[str]):
    header = "## Actions (click)\n"
    buttons = "\n".join(create_button(label) for label in labels)
    return header + buttons
