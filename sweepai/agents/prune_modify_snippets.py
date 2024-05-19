"""
Input: snippets output: snippets to keep
"""

import re

from loguru import logger

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel

system_message_prompt = """You are a genius engineer tasked with identifying only the necessary code snippets for the following code change.
You have been provided with the relevant metadata to the issue.
Please identify only the necessary snippets. If there are none, return an empty response.

You will be given the old_file and potentially relevant code snippets. Describe the changes that should be made, and finally select the necessary snippets for the request.

Respond in the following format:

<snippets_and_plan_analysis file="file_path">
Describe what should be changed to the snippets from the old_file to complete the request.
Then, for each snippet in a list, determine whether changes should be made. If so, describe the changes needed.
Maximize information density.
</snippets_and_plan_analysis>

<snippets_to_edit>
<index>0</index>
...
<index>n</index>
</snippets_to_edit>"""

user_prompt = """# Code
File path: {file_path}
{old_code}
{changes_made}
# Original request
{request}

<snippets>
{snippets}
</snippets>

Analyse the snippets and plan, and provide your response in the format:

<snippets_and_plan_analysis file="file_path">
Describe what should be changed to the snippets from the old_file to complete the request.
Then, for each snippet in a list, determine whether changes should be made. If so, describe the changes needed.
Maximize information density.
</snippets_and_plan_analysis>

<snippets_to_edit>
<index>
0
</index>
...
<index>
n
</index>
</snippets_to_edit>"""


class PrunedSnippets(RegexMatchableBaseModel):
    snippet_indices: list[int] = []

    @classmethod
    def from_string(cls, pruned_snippets_response: str, **kwargs) -> "PrunedSnippets":
        snippet_indices = set()
        pruned_snippets_pattern = r"""<index>(\n)?(?P<index>.*?)</index>"""
        for match_ in re.finditer(
            pruned_snippets_pattern, pruned_snippets_response, re.DOTALL
        ):
            index = match_.group("index").strip("\n")
            index = int(index)
            if index is not None:
                snippet_indices.add(index)
        if len(snippet_indices) > 0:
            snippet_indices.add(0)
        snippet_indices = list(snippet_indices)
        return cls(
            snippet_indices=snippet_indices,
        )


class PruneModifySnippets(ChatGPT):
    def prune_modify_snippets(
        self,
        snippets: list[str],
        file_path: str,
        changes_made: str,
        old_code: str,
        request: str,
        **kwargs,
    ) -> list[int]:
        try:
            if old_code:
                old_code = f"<old_code>\n```\n{old_code}\n```\n</old_code>"
            self.messages[0] = Message(
                role="system", content=system_message_prompt, key="system"
            )
            response = self.chat(
                user_prompt.format(
                    snippets=snippets,
                    file_path=file_path,
                    changes_made=changes_made,
                    old_code=old_code,
                    request=request,
                )
            )
            snippet_indices = PrunedSnippets.from_string(response)
            return snippet_indices.snippet_indices
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return []


if __name__ == "__main__":
    pruned_snippets_response = """<snippets_to_edit>
<index>0</index>
<index>1</index>
<index>2</index>
</snippets_to_edit>"""
    snippet_indices = PrunedSnippets.from_string(pruned_snippets_response)
    print(snippet_indices.snippet_indices)
