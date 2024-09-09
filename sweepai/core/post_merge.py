import re
import traceback
from typing import TypeVar

from sweepai.config.server import DEFAULT_GPT4_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel
from loguru import logger

system_prompt = """You are a brilliant and meticulous engineer assigned to review the following commit diffs and make sure the file conforms to the user's rules.
If the diffs do not conform to the rules, we should create a GitHub issue telling the user what changes should be made.

Provide your response in the following format:

<rule_analysis>
- Analysis of each file_diff and whether it breaks the rule
...
</rule_analysis>

<changes_required>
Output "True" if the rule is broken, "False" otherwise
</changes_required>

<issue_title>
Write an issue title describing what file and rule to fix.
</issue_title>

<issue_description>
GitHub issue description for what we want to solve. Give general instructions on how to solve it. Mention files to take a look at and other code pointers.
</issue_description>"""

user_message = """Review the following diffs and make sure they conform to the rules:
{diff}

The rule is: {rule}

Provide your response in the following format:

<rule_analysis>
- Analysis of code diff 1 and whether it breaks the rule
- Analysis of code diff 2 and whether it breaks the rule
...
</rule_analysis>

<changes_required>
Output "True" if the rule is broken, "False" otherwise
</changes_required>

<issue_title>
Write an issue title describing what file and rule to fix.
</issue_title>

<issue_description>
GitHub issue description for what we want to solve. Give general instructions on how to solve it. Mention files to take a look at and other code pointers.
</issue_description>"""

Self = TypeVar("Self", bound="RegexMatchableBaseModel")


class IssueTitleAndDescription(RegexMatchableBaseModel):
    changes_required: bool = False
    issue_title: str
    issue_description: str

    @classmethod
    def from_string(cls: type["IssueTitleAndDescription"], string: str, **kwargs) -> "IssueTitleAndDescription":
        changes_required_pattern = (
            r"""<changes_required>(\n)?(?P<changes_required>.*)</changes_required>"""
        )
        changes_required_match = re.search(changes_required_pattern, string, re.DOTALL)
        changes_required = (
            changes_required_match.groupdict()["changes_required"].strip()
            if changes_required_match
            else None
        )
        if changes_required and "true" in changes_required.lower():
            changes_required = True
        else:
            changes_required = False
        issue_title_pattern = r"""<issue_title>(\n)?(?P<issue_title>.*)</issue_title>"""
        issue_title_match = re.search(issue_title_pattern, string, re.DOTALL)
        issue_title = (
            issue_title_match.groupdict()["issue_title"].strip()
            if issue_title_match
            else ""
        )
        issue_description_pattern = (
            r"""<issue_description>(\n)?(?P<issue_description>.*)</issue_description>"""
        )
        issue_description_match = re.search(
            issue_description_pattern, string, re.DOTALL
        )
        issue_description = (
            issue_description_match.groupdict()["issue_description"].strip()
            if issue_description_match
            else ""
        )
        return cls(
            changes_required=changes_required,
            issue_title=issue_title,
            issue_description=issue_description,
        )


class PostMerge(ChatGPT):
    def check_for_issues(self, rule, diff) -> tuple[bool, str, str]:
        try:
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt.format(rule=rule),
                    key="system",
                )
            ]
            if self.chat_logger and not self.chat_logger.is_paying_user():
                raise ValueError("User is not a paying user")
            self.model = DEFAULT_GPT4_MODEL
            response = self.chat(
                user_message.format(
                    rule=rule,
                    diff=diff,
                )
            )
            issue_title_and_description = IssueTitleAndDescription.from_string(response)
            return (
                issue_title_and_description.changes_required,
                issue_title_and_description.issue_title,
                issue_title_and_description.issue_description,
            )
        except Exception:
            logger.error(f"An error occurred: {traceback.print_exc()}")
            return False, "", ""


if __name__ == "__main__":
    changes_required_response = """<rule_analysis>
- Analysis of code diff 1 and whether it breaks the rule
The code diff 1 does not break the rule. There are no docstrings or comments that need to be updated.

- Analysis of code diff 2 and whether it breaks the rule
The code diff 2 breaks the rule. There is a commented out code block that should be removed.

</rule_analysis>

<changes_required>
True if the rule is broken, False otherwise
True

</changes_required>

<issue_title>
Outdated Commented Code Block in plan-list.blade.php
</issue_title>

<issue_description>
There is an outdated commented out code block in the file `resources/views/livewire/plan-list.blade.php` that should be removed. The code block starts at line 104 and ends at line 110. Please remove this code block as it is no longer needed.

Please refer to the file `resources/views/livewire/plan-list.blade.php` and remove the commented out code block starting at line 104 and ending at line 110.

</issue_description>"""
    changes_required = IssueTitleAndDescription.from_string(changes_required_response)
