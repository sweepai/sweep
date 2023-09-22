from typing import List

from sweepai.events import IssueCommentChanges, Changes


def create_button(name: str, value: str, text: str, style: str, confirm: dict, selected: bool = False):
    return {
        "type": "button",
        "name": name,
        "value": value,
        "text": text,
        "style": style,
        "confirm": confirm,
        "selected": selected
    }


def create_action_buttons(labels: List[str], header="## Actions (click)\n"):
    buttons = "\n".join(create_button(label, "value", "text", "style", {}) for label in labels)
    return header + buttons


def get_toggled_state(label: str, changes_request: Changes) -> bool:
    old_content = changes_request.body_from
    button = create_button(label, "value", "text", "style", {}, selected=True)
    return button['name'].lower() in old_content.lower()


def check_button_activated(
    button: dict, body: str, changes_request: Changes | None = None
) -> bool:
    if changes_request:
        if get_toggled_state(button['name'], changes_request):
            # If the issue was previously activated, do not activate it again
            return False

    return button['name'].lower() in body.lower()
