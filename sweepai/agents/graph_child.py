import re
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel

system_prompt = """You are a genius engineer tasked with extracting information to complete the following issue listed in metadata.

First, you must determine what information is necessary. Extract the code you deem necessary, and then determine whether a plan for modifying this file is necessary.

# Extraction

Thoughts:
- {thought about this file and its relevance to the issue}
...

<relevant_snippets>
{relevant snippets from repo}
</relevant_snippets>

<plan_for_file>
{plan for modifying this file if necessary. If not, leave blank}
</plan_for_file>"""

graph_user_prompt = """
<file file_path=\"{file_path}\" entity=\"{entity}\">
{code}
</file>

<metadata>
{issue_metadata}
</metadata>

Complete the Extraction step by extracting the relevant snippets from the file above.
"""

class GraphContextAndPlan(RegexMatchableBaseModel):
    relevant_snippets: str
    plan_for_file: str
    file_path: str = None
    entity: str = None

    @classmethod
    def from_string(cls, string: str, **kwargs):
        pattern = r"""<relevant_snippets>(\n)?(?P<relevant_snippets>.*)</relevant_snippets>.*?<plan_for_file>(\n)?(?P<plan_for_file>.*)</plan_for_file>"""
        match = re.search(pattern, string, re.DOTALL)
        relevant_snippets = None
        plan_for_file = None
        if match:
            relevant_snippets = match.group("relevant_snippets")
            plan_for_file = match.group("plan_for_file")
        return cls(
            relevant_snippets=relevant_snippets, plan_for_file=plan_for_file, **kwargs
        )

    def __str__(self) -> str:
        return f"{self.relevant_snippets}\n{self.plan_for_file}"
    
class GraphChildBot(ChatGPT):
    def code_plan_extraction(
        self, code, file_path, entity, issue_metadata,
    ) -> GraphContextAndPlan:
        self.messages = [
            Message(
                role="system",
                content=system_prompt,
                key="system",
            )
        ]
        user_prompt = graph_user_prompt.format(
            code=code,
            file_path=file_path,
            entity=entity,
            issue_metadata=issue_metadata,
        )
        self.model = (
            "gpt-4-32k"
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else "gpt-3.5-turbo-16k-0613"
        )
        response = self.chat(user_prompt)
        graph_plan = GraphContextAndPlan.from_string(response)
        graph_plan.file_path = file_path
        graph_plan.entity = entity
        return graph_plan