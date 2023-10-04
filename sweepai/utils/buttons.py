from typing import List

from sweepai.events import Changes


def create_button(label: str, selected: bool = False) -> str:
    """Create a button for the issue body."""
    return f"- [{'x' if selected else ' '}] {label}"


REVERT_BUTTON = "sweep: revert"
REGENERATE_BUTTON = "sweep: regenerate"

def create_action_buttons(labels: List[str], revert_button: str = REVERT_BUTTON, regenerate_button: str = REGENERATE_BUTTON, header="## Actions (click)\n") -> str:
    """Create a list of buttons for the issue body."""
    labels.append(revert_button)
    labels.append(regenerate_button)
    buttons = "\n".join(create_button(label) for label in labels)
    return header + buttons


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
