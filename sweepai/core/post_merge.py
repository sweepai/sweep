import traceback
from logn import logger
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import IssueTitleAndDescription, Message

system_prompt = """Your name is Sweep bot. You are a brilliant and meticulous engineer assigned to review the following file and make sure the file conforms to the user's rules.

If the file does not conform to the rules, we should create a GitHub issue telling the user what rules were broken and what changes should be made.

The rules are as such.
<rules>
{rules}
</rules>

Your job is to review the file for each rule and then create a GitHub issue.
"""

rule_section = """{rule} - whether it is broken:
* Thought 1 - Explanation 1 with code references
* Thought 2 - Explanation 2 with code references
..."""

user_message = """Review the following file and make sure it conforms to the rules:
<file="{file_path}">
{file_contents}
</file>

Provide your response in the following format:

Step-by-step thoughts with explanations:
{rule_sections}

Whether changes are required:
<changes_required>True/False</changes_required>

Github Issue Title:
<issue_title>
Issue title referencing the file path, changes, and any function/class names. This should be imperative rather than descriptive.
</issue_title>

GitHub Issue Description:
<issue_description>
Issue description with a detailed description of where we should change the code, referencing code snippets to make the changes.
</issue_description>"""


class PostMerge(ChatGPT):
    def check_for_issues(self, rules, file_path, file_contents) -> tuple[str, str]:
        try:
            rules_str = "\n".join(rules)
            self.messages = [
                Message(
                    role="system",
                    content=system_prompt.format(rules=rules_str),
                    key="system",
                )
            ]
            rule_sections = "\n".join(
                [rule_section.format(rule=rule) for rule in rules]
            )
            issues_prompt = user_message.format(
                file_path=file_path,
                file_contents=file_contents,
                rule_sections=rule_sections,
            )
            self.model = (
                "gpt-4-32k"
                if (self.chat_logger and self.chat_logger.is_paying_user())
                else "gpt-3.5-turbo-16k-0613"
            )
            response = self.chat(issues_prompt)
            issue_title_and_description = IssueTitleAndDescription.from_string(response)
            if issue_title_and_description.changes_required:
                return (
                    issue_title_and_description.issue_title,
                    issue_title_and_description.issue_description,
                )
            else:
                logger.info("No issues found")
                return "", ""
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(f"An error occurred: {traceback.print_exc()}")
            return "", ""
