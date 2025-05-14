import re
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet
from sweepai.utils.majority_vote import majority_vote_decorator
from collections import Counter

type_to_explanation = {
    "source": "This is the source code of the software.",
    "tests": "These are the test files in the repository.",
    "tools": "These are tool configurations and scripts used to build, deploy, or manage the software.",
    "dependencies": "These are dependency configurations. They specify the external libraries and packages required by the software.",
    "docs": "These are documentation files. They provide information and instructions about the software.",
}

analyze_system_prompt = """We are trying to solve a GitHub issue. 
The GitHub issue to solve is: 
<issue>
{issue}
</issue>
We are going to check a subset of the code snippets from the repository to identify the most relevant files. We are currently checking: {type_name}. {explanation}

Identify and select ALL of the snippets that are absolutely relevant from the provided snippets. This may be empty if there are no relevant snippets from this type."""

analyze_user_prompt = """The GitHub issue to solve is: 
<issue>
{issue}
</issue>

Here are the {type_name} snippets from the repository. {explanation}
{snippet_text}

Identify and select ALL of the snippets that are absolutely relevant from the provided snippets.

Respond in the following format. Replace the placeholders with the relevant information.
<thinking>
[analysis of snippet_1's relevance]
[analysis of snippet_2's relevance]
...
[analysis of snippet_n's relevance]
</thinking>

<relevant_snippets>
<relevant_snippet>
snippet_path_1
</relevant_snippet>
<relevant_snippet>
snippet_path_2
</relevant_snippet>
...
</relevant_snippets>

Please provide the relevant snippets from the repository. This may be empty if there are no relevant snippets from this type."""

def snippet_majority_vote(outcomes: list[list[Snippet]]):
    # Flatten the list of lists into a single list of snippets
    all_snippets = [snippet for outcome in outcomes for snippet in outcome]

    # Count the occurrences of each snippet
    snippet_counts = Counter(all_snippets)

    # Get the total number of outcomes
    num_outcomes = len(outcomes)

    # Filter the snippets that were selected by all outcomes
    majority_snippets = [
        snippet for snippet, count in snippet_counts.items()
        if count == num_outcomes # strict
    ]
    return majority_snippets

class AnalyzeSnippetAgent(ChatGPT):
    @majority_vote_decorator(num_samples=2, voting_func=snippet_majority_vote) # unsure about 3 vs 1
    def analyze_snippets(self, snippets: list[Snippet], type_name: str, issue: str, seed: int=0):
        # should a subset of the relevant snippets from a slice of the repo
        snippet_text = self.format_code_snippets(snippets)
        system_prompt = analyze_system_prompt.format(issue=issue, type_name=type_name, explanation=type_to_explanation[type_name])
        self.messages = [Message(role="system", content=system_prompt)]
        user_prompt = analyze_user_prompt.format(issue=issue, type_name=type_name, explanation=type_to_explanation[type_name], snippet_text=snippet_text)
        analyze_response = self.chat_anthropic(
            content=user_prompt,
            temperature=0.3, # we have majority voting
            model="claude-3-haiku-20240307",
            seed=seed,
        )
        relevant_snippet_pattern = r"<relevant_snippet>\n(.*?)\n</relevant_snippet>"
        relevant_snippets = re.findall(relevant_snippet_pattern, analyze_response, re.DOTALL)
        relevant_snippets = set(snippet.strip() for snippet in relevant_snippets)
        remaining_snippets = [snippet for snippet in snippets if snippet.file_path in relevant_snippets]
        return remaining_snippets

    def format_code_snippets(self, code_snippets: list[Snippet]):
        result_str = ""
        for idx, snippet in enumerate(code_snippets):
            snippet_str = \
f'''
<snippet index="{idx + 1}">
<snippet_path>{snippet.file_path}</snippet_path>
<source>
{snippet.get_snippet(False, False)}
</source>
</snippet>
'''
            result_str += snippet_str + "\n"
        result_removed_trailing_newlines = result_str.rstrip("\n")
        return result_removed_trailing_newlines
