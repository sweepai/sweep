from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, Snippet

type_to_explanation = {
    "source": "This is the source code. The files contain the actual implementation of the software.",
    "tests": "These the tests. They contain the tests that verify the correctness of the implementation.",
    "tools": "These are tool configurations and scripts. They are used to build, deploy, or manage the software.",
    "dependencies": "These are dependency configurations. They specify the external libraries and packages required by the software.",
    "docs": "These are documentation files. They provide information and instructions about the software.",
}

analyze_system_prompt = """We are trying to solve a GitHub issue. 
The GitHub issue to solve is: 
<issue>
{issue}
</issue>
We are going to check a subset of the code snippets from the repository to identify the most relevant files. We are currently checking: {type_name}. {explanation}

Please provide the relevant snippets from the repository. This may be empty if there are no relevant snippets from this type."""

analyze_user_prompt = """The GitHub issue to solve is: 
<issue>
{issue}
</issue>

Here are the {type_name} snippets from the repository. {explanation}
{snippet_text}

Identify and select all snippets that may be relevant from the provided snippets.

Respond in the following format. Replace the placeholders with the relevant information.
<thinking>
[analysis of snippet_1]
[analysis of snippet_2]
...
</thinking>

<relevant_snippets>
<relevant_snippet>
[file_name]
</relevant_snippet>
<relevant_snippet>
[file_name]
</relevant_snippet>
...
</relevant_snippets>

Please provide the relevant snippets from the repository. This may be empty if there are no relevant snippets from this type."""

class AnalyzeSnippetAgent(ChatGPT):
    def analyze_snippets(self, snippets: list[Snippet], type_name: str, issue: str):
        # should a subset of the relevant snippets from a slice of the repo
        snippet_text = format(self.format_code_snippets(snippets))
        system_prompt = analyze_system_prompt.format(issue=issue, type_name=type_name, explanation=type_to_explanation[type_name])
        self.messages = [Message(role="system", content=system_prompt)]
        user_prompt = analyze_user_prompt.format(issue=issue, type_name=type_name, explanation=type_to_explanation[type_name], snippet_text=snippet_text)
        analyze_response = self.chat_anthropic(
            content=user_prompt,
            temperature=0.2,
            use_openai=True
        )
        pass
        return snippets

    def format_code_snippets(self, code_snippets: list[Snippet]):
        result_str = ""
        for idx, snippet in enumerate(code_snippets):
            snippet_str = \
f'''
<snippet index="{idx + 1}">
<snippet_path>{snippet.denotation}</snippet_path>
<source>
{snippet.get_snippet(False, False)}
</source>
</snippet>
'''
            result_str += snippet_str + "\n"
        result_removed_trailing_newlines = result_str.rstrip("\n")
        return result_removed_trailing_newlines
