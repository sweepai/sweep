import re
from typing import List

from sweepai.web.events import Changes


def create_button(label: str, selected: bool = False) -> str:
    """Create a button for the issue body."""
    return f"- [{'x' if selected else ' '}] {label}"


def create_action_buttons(labels: List[str], header="## Actions\n") -> str:
    """Create a list of buttons for the issue body."""
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


def check_button_title_match(
    title: str, body: str, changes_request: Changes | None = None
):
    if changes_request:
        content = changes_request.body_from or ""
        if title.lower() in content.lower():
            return True
    return False


class Button:
    def __init__(self, label: str, selected: bool = False):
        self.label = label
        self.selected = selected

    def __str__(self):
        return f"- [{'x' if self.selected else ' '}] {self.label}"


class ButtonList:
    def __init__(self, title: str = "", buttons: List[Button] = None):
        self.title = title
        self.buttons = buttons or []

    def serialize(self) -> str:
        return f"{self.title}\n" + "\n".join(str(button) for button in self.buttons)

    @classmethod
    def deserialize(cls, message: str):
        lines = message.split("\n")
        title = lines[0]
        button_pattern = r"- \[(?P<state>[ x])\] (?P<label>.+)"
        matches = re.findall(button_pattern, message)
        buttons = [Button(label, state == "x") for state, label in matches]
        return cls(title, buttons)

    def get_clicked_buttons(self) -> List[Button]:
        return [button for button in self.buttons if button.selected]


if __name__ == "__main__":
    # Example serialized string (str -> buttons)
    serialized_str = """## My Favorite Foods
    - [x] Pizza
    - [x] Burger
    - [x] Sushi"""

    # Deserialize the string to get a ButtonList object
    deserialized_btn_list = ButtonList.deserialize(serialized_str)

    # Display the deserialized list
    print(f"Title: {deserialized_btn_list.title}")
    for btn in deserialized_btn_list.buttons:
        print(btn)

    # Get clicked buttons
    clicked_buttons = deserialized_btn_list.get_clicked_buttons()
    print("\nClicked Buttons:")
    for btn in clicked_buttons:
        print(btn)
