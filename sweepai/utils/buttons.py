from typing import List

DISCORD_FEEDBACK_WEBHOOK_URL = "https://discord.com/api/webhooks/your-webhook-id"


from sweepai.events import IssueCommentChanges, Changes

def report_to_discord(webhook_url: str, message: str):
    # This is a placeholder function. Replace this with the actual implementation.
    pass

def create_button(label: str, selected: bool = False):
    return f"- [{'x' if selected else ' '}] {label}"

def handle_feedback(feedback: str):
    if feedback.startswith("Feedback: "):
        # Assuming that the `report_to_discord` function is already defined and takes the webhook URL and message as parameters
        report_to_discord(DISCORD_FEEDBACK_WEBHOOK_URL, feedback)

def create_action_buttons(labels: List[str], header="## Actions (click)\n"):
    buttons = "\n".join(create_button(label) for label in labels)
    buttons += "\n- [ ] Feedback: "
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
    if button.lower() in body.lower():
        feedback_start = body.lower().find("feedback: ")
        if feedback_start != -1:
            feedback_end = body.lower().find("\n", feedback_start)
            feedback = body[feedback_start:feedback_end]
            handle_feedback(feedback)
        return True
    return False
