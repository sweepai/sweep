from dataclasses import dataclass

from sweepai.agents.modify import modify
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Message, Snippet, UnneededEditError
from sweepai.utils.autoimport import add_auto_imports
from sweepai.utils.event_logger import posthog
from sweepai.utils.github_utils import ClonedRepo
from sweepai.utils.progress import AssistantConversation, TicketProgress

fetch_snippets_system_prompt = """You are a masterful engineer. Your job is to extract the original sections from the code that should be modified.

Extract the smallest spans that let you handle the request by adding sections of sections_to_modify containing the code you want to modify. Use this for implementing or changing functionality.

<analysis_and_identification file="file_path">
Identify all changes that need to be made to the file.
Check the diff to make sure the changes have not previously been completed in this file.
In a list, identify all code sections that should receive these changes and all locations code should be added. These sections will go into the sections_to_modify block.
</analysis_and_identification>

<sections_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
...
</sections_to_modify>"""

fetch_snippets_prompt = """# Code
File path: {file_path}
<sections>
```
{code}
```
</sections>
{changes_made}
# Request
{request}

# Instructions
{chunking_message}

# Format
<analysis_and_identification file="file_path">
Identify all changes that need to be made to the file.
In a list, identify all code sections that should receive these changes and all locations code should be added. These sections will go into the sections_to_modify block.
</analysis_and_identification>

<sections_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
...
</sections_to_modify>"""

fetch_snippets_prompt_with_diff = """# Code
File path: {file_path}
<sections>
```
{code}
```
</sections>
{changes_made}
# Request
{request}

# Instructions
{chunking_message}

# Format
<analysis_and_identification file="file_path">
Identify all changes that need to be made to the file.
Check the diff to make sure the changes have not previously been completed in this file.
In a list, identify all code sections that should receive these changes and all locations code should be added. These sections will go into the sections_to_modify block.
</analysis_and_identification>

<sections_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
...
</sections_to_modify>"""

plan_snippets_system_prompt = """\
You are a brilliant and meticulous engineer assigned to plan code changes to complete the user's request.

You will plan code changes to solve the user's problems. You have the utmost care for the plans you write, so you do not make mistakes and you fully implement every function and class. Take into account the current repository's language, code style, and dependencies.

You will be given the old_file and potentially relevant snippets to edit. You do not necessarily have to edit all the snippets.

Respond in the following format:

<snippets_and_plan_analysis file="file_path">
Describe what should be changed to the snippets from the old_file to complete the request.
Then, for each snippet, describe in natural language in a list the changes needed, with references to the lines that should be changed and what to change it to.
Maximize information density and conciseness but be detailed.
</snippets_and_plan_analysis>"""

plan_snippets_prompt = """# Code
File path: {file_path}
<old_code>
```
{code}
```
</old_code>
{changes_made}
# Request
{request}

<snippets_to_update>
{snippets}
</snippets_to_update>

# Instructions
Describe all changes that should be made.

Respond in the following format:

<snippets_and_plan_analysis file="file_path">
Describe what should be changed to the snippets from the old_file to complete the request.
Then, for each snippet, describe in natural language in a list the changes needed, with references to the lines that should be changed and what to change it to.
Maximize information density and conciseness but be detailed.
</snippets_and_plan_analysis>"""


UPDATE_SNIPPETS_MAX_TOKENS = 1450


def get_last_import_line(code: str, max_: int = 150) -> int:
    lines = code.split("\n")
    for i, line in enumerate(reversed(lines)):
        if line.startswith("import ") or line.startswith("from "):
            return min(len(lines) - i - 1, max_)
    return -1


@dataclass
class SnippetToModify:
    snippet: Snippet
    reason: str


@dataclass
class MatchToModify:
    start: int
    end: int
    reason: str


def strip_backticks(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s[s.find("\n") :]
    if s.endswith("```"):
        s = s[: s.rfind("\n")]
    s = s.strip("\n")
    if s == '""':
        return ""
    return s


def convert_comment_to_deletion(original, updated):
    # check both are single lines
    if "\n" in original or "\n" in updated:
        return updated
    # check both are not empty
    if original == "" or updated == "":
        return updated
    # if original not a comment and updated is a comment, then it's a deletion
    if not original.startswith("#") and updated.startswith("#"):
        return ""
    return updated


class ModifyBot:
    def __init__(
        self,
        additional_messages: list[Message] = [],
        chat_logger=None,
        parent_bot: ChatGPT = None,
        old_file_contents: str = "",
        current_file_diff: str = "",
        ticket_progress: TicketProgress | None = None,
        **kwargs,
    ):
        self.chat_logger = chat_logger
        self.additional_messages = additional_messages
        self.old_file_contents = old_file_contents
        self.current_file_diff = current_file_diff
        self.additional_diffs = ""
        self.ticket_progress = ticket_progress

    def try_update_file(
        self,
        instructions: str,
        cloned_repo: ClonedRepo,
        assistant_conversation: AssistantConversation | None = None,
        seed: str | None = None,
        relevant_filepaths: list[str] = [],
        fcrs: list[FileChangeRequest]=[],
        previous_modify_files_dict: dict[str, dict[str, str | list[str]]] = None,
    ):
        new_files = modify(
            request=instructions,
            cloned_repo=cloned_repo,
            relevant_filepaths=relevant_filepaths,
            fcrs=fcrs,
        )
        if new_files:
            posthog.capture(
                (
                    self.chat_logger.data["username"]
                    if self.chat_logger is not None
                    else "anonymous"
                ),
                "function_modify_succeeded",
                {
                    "repo_full_name": cloned_repo.repo_full_name,
                },
            )
            # new_file is now a dictionary
            for file_path, new_file_data in new_files.items():
                new_file_data["contents"] = add_auto_imports(file_path, cloned_repo.repo_dir, new_file_data["contents"], run_isort=False)
            return new_files
        posthog.capture(
            (
                self.chat_logger.data["username"]
                if self.chat_logger is not None
                else "anonymous"
            ),
            "function_modify_succeeded",
            {
                "repo_full_name": cloned_repo.repo_full_name,
            },
        )
        raise UnneededEditError("No snippets edited")

if __name__ == "__main__":
    try: 
        from sweepai.utils.github_utils import get_installation_id, ClonedRepo
        from loguru import logger
        organization_name = "sweepai"
        installation_id = get_installation_id(organization_name)
        cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")
        additional_messages = [Message(
                role="user",
                content="""# Repo & Issue Metadata
Repo: sweepai/sweep: sweep
add an import math statement at the top of the api.py file""",
            ), Message(
                role="user",
                content=f"<relevant_file file_path='sweepai/api.py'>\n{open(cloned_repo.repo_dir + '/' + 'sweepai/api.py').read()}\n</relevant_file>",
                key="instructions",
            )]
        modify_bot = ModifyBot(
            additional_messages=additional_messages
        )
        new_files = modify_bot.try_update_file(
            "sweepai/api.py",
            open(cloned_repo.repo_dir + '/' + 'sweepai/api.py').read(),
            FileChangeRequest(
                filename="sweepai/api.py",
                instructions="add an import math statement at the top of the api.py file",
                change_type="modify"
            ),
            cloned_repo,
        )
        new_file = new_files["sweepai/api.py"]["contents"]
        assert("import math" in new_file)
        response = """
```python
```"""
        stripped = strip_backticks(response)
        print(stripped)
    except Exception as e:
        logger.error(f"sweep_bot.py failed to run successfully with error: {e}")
