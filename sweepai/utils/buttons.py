from typing import List

from sweepai.events import Changes


def create_button(label: str, selected: bool = False) -> str:
    """Create a button for the issue body."""
    timestamp = datetime.now().isoformat()
    return f"- [{'x' if selected else ' '}] {label} {timestamp}"
    """Create a button for the issue body."""
    return f"- [{'x' if selected else ' '}] {label}"


def create_action_buttons(labels: List[str], header="## Actions (click)\n") -> str:
    """Create a list of buttons for the issue body."""
    def get_toggled_state(label: str, changes_request: Changes) -> bool:
        """Get the toggled state of a button."""
        old_content = changes_request.body_from
        button = create_button(label, selected=True)
        button_timestamp = parse_timestamp_from_button(button)
        request_timestamp = parse_timestamp_from_request(changes_request)
        return button.lower() in old_content.lower() and button_timestamp < request_timestamp
    
    
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
