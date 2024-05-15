import re

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message

system_prompt = """Remove any completely irrelevant text from the issue description. Keep relevant instructions, stacktraces and informative debugging information. Further, reformat any code with broken formatting."""

prompt = """\
<issue_description>
{issue_description}
</issue_description>

Remove any completely irrelevant text from the issue description. Keep relevant instructions, stacktraces and informative debugging information. Further, reformat any code with broken formatting. Copy as much text verbatim as possible.

Explain what needs to be removed.
Then format your response in <new_issue_description> tags:"""


class IssueCleanupBot(ChatGPT):
    def cleanup_issue(
        self,
        issue_description,
    ):
        new_issue_desc_pattern = r"<new_issue_description>(.*?)</new_issue_description>"
        self.messages = [
            Message(
                content=system_prompt,
                role="system",
            ),
        ]
        issue_desc_response = self.chat( # gpt4 04-09 had a better one in minimal (1 example) testing, seems smart
            content=prompt.format(
                issue_description=issue_description.strip("\n"),
            ),
            temperature=0.2,
            model="gpt-4o"
        )
        issue_desc_matches = re.search(new_issue_desc_pattern, issue_desc_response, re.DOTALL)
        if not issue_desc_matches or not issue_desc_matches.group(1).strip():
            return issue_description
        issue_desc = issue_desc_matches.group(1)
        issue_desc = issue_desc.strip()
        return issue_desc
