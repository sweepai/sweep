import traceback

from sweepai.logn import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import IssueTitleAndDescription, Message

system_prompt = """Your name is Sweep bot. You are a brilliant and meticulous engineer assigned to review the following commit diffs and make sure the file conforms to the user's rules.
If the diffs do not conform to the rules, we should create a GitHub issue telling the user what changes should be made.

Review the diffs then create a GitHub issue. Give specific instructions on how to solve the issue with file and code references."""

user_message = """Review the following diffs and make sure they conform to the rules:
{diff}

The rule is: {rule}

Provide your response in the following format.
<rule_analysis>
- Analysis of code diff 1 and whether it breaks the rule
- Analysis of code diff 2 and whether it breaks the rule
...
</rule_analysis>

Whether the rule is broken:
<changes_required>
True/False
</changes_required>

Github Issue Title:
<issue_title>
Root cause of the broken rule.
</issue_title>

GitHub Issue Description:
<issue_description>
High level description of what we want to solve. Do not give any instructions on how to solve it. Do mention files to take a look at and other code pointers.
</issue_description>"""


class PostMerge(ChatGPT):
    def check_for_issues(self, rule, diff) -> tuple[str, str]:
        try:
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt.format(rule=rule),
                    key="system",
                )
            ]
            self.model = (
                "gpt-4-32k"
                if (self.chat_logger and self.chat_logger.is_paying_user())
                else "gpt-3.5-turbo-16k-0613"
            )
            response = self.chat(user_message.format(
                rule=rule,
                diff=diff,
            ))
            issue_title_and_description = IssueTitleAndDescription.from_string(response)
            return (
                issue_title_and_description.changes_required,
                issue_title_and_description.issue_title,
                issue_title_and_description.issue_description,
            )
        except SystemExit:
            raise SystemExit
        except Exception:
            logger.error(f"An error occurred: {traceback.print_exc()}")
            return False, "", ""
