from typing import List
import subprocess

from sweepai.events import IssueCommentChanges, Changes


REVERT_BUTTON = "Revert"

def create_button(label: str, selected: bool = False):
    return f"- [{'x' if selected else ' '}] {label}"

def revert_file(file_path: str, commit_hash: str):
    try:
        subprocess.check_call(['git', 'checkout', commit_hash, '--', file_path])
    except subprocess.CalledProcessError as e:
        print(f"Error reverting file {file_path}: {str(e)}")


def create_action_buttons(labels: List[str], header="## Actions (click)\n"):
    buttons = "\n".join(create_button(label) for label in labels)
    return header + buttons


def get_toggled_state(label: str, changes_request: Changes) -> bool:
    old_content = changes_request.body_from
    button = create_button(label, selected=True)
    return button.lower() in old_content.lower()


def check_button_activated(
    label: str, body: str, changes_request: Changes | None = None, file_path: str = None, commit_hash: str = None
) -> bool:
    if changes_request:
        if get_toggled_state(label, changes_request):
            # If the issue was previously activated, do not activate it again
            return False

    button = create_button(label, selected=True)
    if button.lower() in body.lower():
        if label == REVERT_BUTTON and file_path and commit_hash:
            revert_file(file_path, commit_hash)
        return True
    return False
