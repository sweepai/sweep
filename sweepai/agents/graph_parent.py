import re
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel

system_prompt = """You are an experienced software engineer working on a GitHub issue. Use the issue_metadata, relevant_snippets_in_repo, and symbols to determine the best additional sfiles to explore.

The issue metadata, code, symbols, and files will be provided in the below format:

<issue_metadata>
repository metadata
issue title
issue description
</issue_metadata>

<relevant_snippets_in_repo>
<snippet source="file_path_1:start_line-end_line">
relevant code snippet 1
</snippet source>
<snippet source="file_path_2:start_line-end_line">
relevant code snippet 2
</snippet source>
...
<relevant_snippets_in_repo>

<symbols_to_files>
symbols(function, variable, or classes) is used/defined in file
<symbols_to_files>

Provide your answer in the below format:

<symbol_analysis>
Concise explanation of relevant symbol's usage and why it is highly relevant to the issue_metadata
</symbol_analysis>

<relevant_symbols_to_files>
{{symbol}}:{{file_path}}
...
</relevant_symbols_to_files>"""

graph_user_prompt = """<metadata>
{issue_metadata}
</metadata>

{relevant_snippets}

<symbols_to_files>
{symbols_to_files}
</symbols_to_files>"""


class RelevantSymbolsAndFiles(RegexMatchableBaseModel):
    relevant_files_to_symbols: dict[str, str]

    @classmethod
    def from_string(cls, string: str, **kwargs):
        relevant_files_to_symbols = {}
        symbols_to_files_pattern = r"""<relevant_symbols_to_files>(\n)?(?P<symbols_to_files>.*)</relevant_symbols_to_files>"""
        symbols_to_files_match = re.search(symbols_to_files_pattern, string, re.DOTALL)
        if symbols_to_files_match:
            symbols_to_files = symbols_to_files_match.group("symbols_to_files")
            for line in symbols_to_files.split("\n"):
                if line:
                    symbol, file_path = line.split(":")
                    relevant_files_to_symbols[file_path] = symbol
        return cls(relevant_files_to_symbols=relevant_files_to_symbols, **kwargs)


class GraphParentBot(ChatGPT):
    def relevant_files_to_symbols(
        self, issue_metadata, relevant_snippets, symbols_to_files
    ):
        self.messages = [
            Message(
                role="system",
                content=system_prompt,
                key="system",
            )
        ]
        user_prompt = graph_user_prompt.format(
            issue_metadata=issue_metadata,
            relevant_snippets=relevant_snippets,
            symbols_to_files=symbols_to_files,
        )
        self.model = (
            "gpt-4-32k"
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else "gpt-3.5-turbo-16k-0613"
        )
        response = self.chat(user_prompt)
        relevant_symbols_and_files = RelevantSymbolsAndFiles.from_string(response)
        return relevant_symbols_and_files.relevant_files_to_symbols


if __name__ == "__main__":
    example_output = """<symbol_analysis>
The issue is about refactoring the messages in the ChatGPT class in the core chat file. The ChatGPT class is defined in the sweepai/core/chat.py file and is used in several other files such as sweepai/core/edit_chunk.py, sweepai/core/external_searcher.py, sweepai/core/documentation_searcher.py, etc. This indicates that any changes to the ChatGPT class will have a wide impact across the codebase.
The issue also mentions migrating the messages variable to a new type called Messages. The Message class is defined in the sweepai/core/entities.py file. This class is likely to be closely related to the new Messages class that needs to be created.
The issue also mentions the need for the Messages class to support with statements, which implies the implementation of enter and exit methods. These methods are not explicitly defined in the provided code snippets, but they are standard methods in Python for managing context in with statements.
The issue also mentions moving the Messages class to the entities python file. The entities file is likely to be sweepai/core/entities.py where the Message class is defined.
Therefore, the ChatGPT class, the Message class, and the entities file are highly relevant to the issue.
</symbol_analysis>

<relevant_symbols_to_files>
ChatGPT:sweepai/core/chat.py
Message:sweepai/core/entities.py
entities:sweepai/core/entities.py
</relevant_symbols_to_files>"""
