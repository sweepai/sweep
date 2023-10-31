import re

import rope.base.project
from rope.refactor.move import MoveGlobal

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message
from sweepai.utils.github_utils import ClonedRepo

system_prompt = """You are a brilliant and meticulous engineer assigned to decide where to move code to help the user refactor their codebase. You specialize in Python programming. Take into account the current repository's language, code style, and dependencies.

You will be given the old_file and relevant snippets to edit. Respond in the following format:

<moves>
<move
    from_file="src/utils/main.py"
    entity="foo"
    destination_module="src.utils.foo_utils"
/>
</moves>"""

user_prompt = """# Code
File path: {file_path}
<old_code>
```
{code}
```
</old_code>
{changes_made}
# Request
{request}

# Instructions
Indicate which snippets should be moved to the destination module.

Respond in the following format:

<moves>
<move
    from_file="src/utils/main.py"
    entity="foo"
    destination_module="src.utils.foo_utils"
/>
</moves>
"""


def move_function(
    file_path: str, method_name: str, destination: str, project_name: str
):
    project = rope.base.project.Project(project_name)

    resource = project.get_resource(file_path)
    func_def = f"def {method_name}("
    offset = resource.read().find(func_def) + len("def ")

    mover = MoveGlobal(project, resource, offset)
    change_set = mover.get_changes(destination)
    for change in change_set.changes:
        change.do()
    result = resource.read()
    return result, change_set


class MoveBot(ChatGPT):
    def refactor_snippets(
        self,
        additional_messages: list[Message] = [],
        file_path: str = "",
        contents: str = "",
        request="",
        changes_made="",
        cloned_repo: ClonedRepo = None,
        **kwargs,
    ):
        self.model = (
            "gpt-4-32k-0613"
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else "gpt-3.5-turbo-16k-0613"
        )
        self.messages = [
            Message(
                role="system",
                content=system_prompt,
                key="system",
            )
        ]
        self.messages.extend(additional_messages)
        move_response = self.chat(
            user_prompt.format(
                code=contents,
                file_path=file_path,
                request=request,
                changes_made=changes_made,
            )
        )
        move_pattern = r'<move\s+from_file="(?P<from_file>.*?)"\s+entity="(?P<entity>.*?)"\s+destination_module="(?P<destination_module>.*?)"\s+/>'
        move_matches = list(re.finditer(move_pattern, move_response, re.DOTALL))
        change_sets = []
        new_code = None
        for idx, match_ in enumerate(move_matches):
            match = match_.groupdict()
            from_file = match["from_file"]
            entity = match["entity"]
            destination_module = match["destination_module"]
            new_code, change_set = move_function(
                from_file, entity, destination_module, cloned_repo.cache_dir
            )
            change_sets.append(change_set)
        for change_set in change_sets:
            for change in change_set.changes:
                change.undo()
        return new_code


if __name__ == "__main__":
    additional_messages = [
        Message(
            role="user",
            content="""Repo: sweep: Sweep: AI-powered Junior Developer for small features and bug fixes.
Issue Title: refactor vector_db.py by pulling common functions and patterns out and putting them in the same function
Issue Description: ### Details

_No response_""",
            key="user",
        )
    ]
    file_path = "sweepai/core/vector_db.py"
    request = "* Move the `get_comment_header` and `custom_config` functions from `sweepai/handlers/on_ticket.py` to `sweepai/utils/ticket_utils.py`.\n\n* Ensure that the functions are placed in a logical location within `ticket_utils.py`, such as at the end of the file."
    changes_made = ""
    bot = MoveBot()
    bot.refactor_snippets(
        additional_messages=additional_messages,
        file_path=file_path,
        request=request,
        changes_made=changes_made,
    )
