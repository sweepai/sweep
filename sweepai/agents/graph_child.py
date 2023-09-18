import re
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel, Snippet

system_prompt = """You are a genius engineer tasked with extracting information to complete the following issue listed in metadata.

First, you must determine what information is necessary. Extract the code you deem necessary, and then determine which code changes in this file are necessary.

# Extraction

Include only the relevant snippets and required file imports that provide enough detail about the snippets to solve the issue:
Select only the relevant lines from these files. Keep the 
relevant_snippets as small as possible. When writing the code changes keep in mind the user can read the metadata and the relevant snippets.

<code_analysis>
{thought about potentially relevant snippet and its relevance to the issue}
...
</code_analysis>

<relevant_snippets>
{relevant snippet from file in the format file_path:start_idx-end_idx (If none, leave this blank)}
...
</relevant_snippets>

<changes_for_file>
{Code changes to make in this file if necessary. If not, leave this blank}
</changes_for_file>"""

graph_user_prompt = """
<metadata>
{issue_metadata}
</metadata>

<file file_path=\"{file_path}\" entity=\"{entity}\">
{code}</file>

Extract the relevant snippets from the file above.
"""

class GraphContextAndPlan(RegexMatchableBaseModel):
    relevant_snippets: list[Snippet]
    plan_for_file: str
    file_path: str = None
    entity: str = None

    @classmethod
    def from_string(cls, string: str, **kwargs):
        snippets_pattern = r"""<relevant_snippets>(\n)?(?P<relevant_snippets>.*)</relevant_snippets>"""
        plan_pattern = r"""<plan_for_file>(\n)?(?P<plan_for_file>.*)</plan_for_file>"""
        snippets_match = re.search(snippets_pattern, string, re.DOTALL)
        relevant_snippets_match = None
        plan_for_file = ""
        relevant_snippets = []
        if not snippets_match:
            return cls(relevant_snippets=relevant_snippets, plan_for_file=plan_for_file, **kwargs)
        relevant_snippets_match = snippets_match.group("relevant_snippets")
        for raw_snippet in relevant_snippets_match.split("\n"):
            if ":" not in raw_snippet:
                continue
            file_path, lines = raw_snippet.split(":", 1)
            file_path, lines = file_path.strip(), lines.split()[0].strip() # second one accounts for trailing text like "1-10 (message)"
            if "-" not in lines:
                continue
            start, end = lines.split("-", 1)
            start = int(start)
            end = int(end) - 1
            end = min(end, start + 200)
            snippet = Snippet(file_path=file_path, start=start, end=end, content="")
            relevant_snippets.append(snippet)
        plan_match = re.search(plan_pattern, string, re.DOTALL)
        if plan_match:
            plan_for_file = plan_match.group("plan_for_file").strip()
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
        code_with_line_numbers = ""
        for i, line in enumerate((r"" + code).split("\n")):
            # TODO: show a window with entity
            code_with_line_numbers += f"{i + 1} {line}\n" + f" <- {entity} is mentioned here\n" if entity in line else f"{i + 1} {line}\n"

        user_prompt = graph_user_prompt.format(
            code=code_with_line_numbers,
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