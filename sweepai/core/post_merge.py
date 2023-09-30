import traceback

from logn import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import IssueTitleAndDescription, Message

system_prompt = """Your name is Sweep bot. You are a brilliant and meticulous engineer assigned to review the following commit diffs and make sure the file conforms to the user's rules.
If the diffs do not conform to the rules, we should create a GitHub issue telling the user what changes should be made.

The rule is: {rule}
Review the diffs then create a GitHub issue.
"""

user_message = """Review the following diffs and make sure they conform to the rules:
{diff}

Provide your response in the following format.
Step-by-step thoughts with explanations:
- Explanation of code change 1 and whether it breaks the rule
- Explanation of code change 2 and whether it breaks the rule
...

Whether the rule is broken:
<changes_required>True/False</changes_required>

Github Issue Title:
<issue_title>
Issue title referencing the file paths, changes, and any function/class names. This should be imperative rather than descriptive.
</issue_title>

GitHub Issue Description:
<issue_description>
Issue description with a detailed description of where we should change the code. Reference files and entities in the code.
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
