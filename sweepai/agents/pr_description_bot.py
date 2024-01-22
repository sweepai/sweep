import re

from sweepai.config.server import DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """\
Write a pull request description that reflects all changes in this pull request. Here are the changes:
<diffs>
{diffs}
</diffs>

Here is the pull request title:
<pr_title>
{pr_title}
</pr_title>

Format your response using the following XML tags:
<pr_description>
# Description
Short description of the pull request.
# Summary
Concise bulleted description of the pull request. Markdown format `variables`, `files`, and `directories` like this.
</pr_description>"""


class PRDescriptionBot(ChatGPT):
    def describe_diffs(
        self,
        diffs,
        pr_title,
    ):
        self.messages = []
        self.model = DEFAULT_GPT35_MODEL
        # attempt to generate description 3 times
        pr_desc_pattern = r"<pr_description>\n(.*?)\n</pr_description>"
        for attempt in [0, 1, 2]:
            pr_desc_response = self.chat(
                content=prompt.format(
                    diffs=diffs,
                    pr_title=pr_title,
                ),
            )
            pr_desc_matches = re.search(pr_desc_pattern, pr_desc_response, re.DOTALL)
            if pr_desc_matches is None:
                if attempt == 2:
                    return ""
            else:
                break
                
        pr_desc = pr_desc_matches.group(1)
        pr_desc = pr_desc.strip()
        return pr_desc
