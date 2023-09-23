from typing import List
import requests

from sweepai.events import IssueCommentChanges, Changes


def create_button(label: str, selected: bool = False):
    return f"- [{'x' if selected else ' '}] {label}"


def create_action_buttons(labels: List[str], header="## Actions (click)\n"):
    DISCORD_FEEDBACK_WEBHOOK_URL = 'https://discordapp.com/api/webhooks/1234567890'
    buttons = "\n".join(create_button(label) for label in labels)
    for label in labels:
        if label.startswith('Feedback: '):
            feedback = label.replace('Feedback: ', '')
            data = {
                "content": f"### PR Feedback: {feedback}\nReply with `Feedback: ...` to leave more detailed feedback."
            }
            requests.post(DISCORD_FEEDBACK_WEBHOOK_URL, data=data)
    return header + buttons


def get_toggled_state(label: str, changes_request: Changes) -> bool:
    old_content = changes_request.body_from
    button = create_button(label, selected=True)
    return button.lower() in old_content.lower()


def check_button_activated(
    label: str, body: str, changes_request: Changes | None = None
) -> bool:
    if changes_request:
        if get_toggled_state(label, changes_request):
            # If the issue was previously activated, do not activate it again
            return False

    button = create_button(label, selected=True)
    return button.lower() in body.lower()
