from typing import List

from sweepai.events import IssueCommentChanges, Changes


def create_button(label: str, selected: bool = False) -> str:
    """Create a button for the issue body."""
    return f"- [{'x' if selected else ' '}] {label}"


from typing import List
import requests

from sweepai.events import IssueCommentChanges, Changes

DISCORD_FEEDBACK_WEBHOOK_URL = "your_webhook_url_here"

def generate_feedback_message(emoji: str) -> str:
    """Generate a feedback message with the given emoji."""
    return f"### PR Feedback: {emoji}\nReply with `Feedback: ...` to leave more detailed feedback."

def create_action_buttons(labels: List[str], header="## Actions (click)\n") -> str:
    """Create a list of buttons for the issue body."""
    buttons = "\n".join(create_button(label) for label in labels)
    feedback_button = create_button("PR Feedback")
    feedback_message = generate_feedback_message("👍")
    if feedback_button in buttons:
        buttons = buttons.replace(feedback_button, feedback_message)
    return header + buttons

from sweepai.utils.buttons import send_feedback_to_discord

def webhook(request):
    event = request.headers.get("X-GitHub-Event")
    payload = request.json

    if event == "issue_comment":
        action = payload["action"]
        comment_body = payload["comment"]["body"]

        if action in ["created", "edited"] and comment_body.startswith("Feedback: "):
            handle_feedback_comment(comment_body)

    # ... rest of the function ...

def handle_feedback_comment(comment_body):
    feedback = comment_body.replace("Feedback: ", "", 1)
    status_code = send_feedback_to_discord(feedback)

    if status_code != 200:
        print(f"Failed to send feedback to discord: status code {status_code}")


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
