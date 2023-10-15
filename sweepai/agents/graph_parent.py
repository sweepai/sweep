from __future__ import annotations

import re

from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Message, RegexMatchableBaseModel

system_prompt = """You are an experienced software engineer working on a GitHub issue. Use the issue_metadata, relevant_snippets_in_repo, and symbols to extract the necessary symbols to solve the issue. Most symbols are not relevant. Provide at most 10 symbols, ideally fewer. They should be in descending order of relevance.

The issue metadata, code, symbols, and files are provided in the below format:

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
Extract the symbols that are needed to solve the issue and explain why. Do not mention it if it's "likely" or "possible", only choose ones you are certain about.
</symbol_analysis>

<relevant_symbols_to_files>
{symbol}:{file_path}
...
</relevant_symbols_to_files>"""

graph_user_prompt = """<metadata>
{issue_metadata}
</metadata>

{relevant_snippets}

<symbols_to_files>
{symbols_to_files}</symbols_to_files>"""


def strip_markdown(contents):
    contents.replace("`", "")
    contents = contents.split(" ")
    contents = [content for content in contents if content]
    return contents


class RelevantSymbolsAndFiles(RegexMatchableBaseModel):
    relevant_files_to_symbols: dict[str, list[str]] = {}
    relevant_symbols_string = ""

    @classmethod
    def from_string(
        cls, string: str, symbols_to_files_string: str, **kwargs
    ) -> RelevantSymbolsAndFiles:
        relevant_files_to_symbols = {}
        symbols_to_files_pattern = r"""<relevant_symbols_to_files>(\n)?(?P<symbols_to_files>.*)</relevant_symbols_to_files>"""
        symbols_to_files_match = re.search(symbols_to_files_pattern, string, re.DOTALL)
        relevant_symbols_string = ""
        if symbols_to_files_match:
            symbols_to_files = symbols_to_files_match.group("symbols_to_files")
            for line in symbols_to_files.split("\n"):
                split = line.split(":")
                if not line or len(split) != 2:
                    continue
                symbol, file_path = split
                symbols = strip_markdown(symbol)
                file_paths = strip_markdown(file_path)
                for file_path in file_paths:
                    # check if file_path is a valid python file
                    if file_path.endswith(".py") and " " not in file_path:
                        relevant_files_to_symbols[file_path] = symbols
            for line in symbols_to_files_string.split("\n"):
                if not line:
                    continue
                symbol, file_path = line.split(" ")[0], line.split(" ")[-1]
                if file_path in relevant_files_to_symbols:
                    relevant_symbols_string += line + "\n"
        return cls(
            relevant_files_to_symbols=relevant_files_to_symbols,
            relevant_symbols_string=relevant_symbols_string,
            **kwargs,
        )


class GraphParentBot(ChatGPT):
    def relevant_files_to_symbols(
        self, issue_metadata: str, relevant_snippets: str, symbols_to_files: str
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
        # self.model = (
        #     "gpt-4-32k-0613"
        #     if (self.chat_logger and self.chat_logger.is_paying_user())
        #     else "gpt-4-32k-0613"
        # )
        self.model = "gpt-4-32k-0613"
        response = self.chat(user_prompt)
        relevant_symbols_and_files = RelevantSymbolsAndFiles.from_string(
            response, symbols_to_files
        )
        return (
            relevant_symbols_and_files.relevant_files_to_symbols,
            relevant_symbols_and_files.relevant_symbols_string,
        )


if __name__ == "__main__":
    response = """<symbol_analysis>
The issue is about refactoring the `messages` variable in the `ChatGPT` class, which is currently a list of `Message` objects. The `Message` class is defined in `sweepai/core/entities.py`. The `ChatGPT` class is defined in `sweepai/core/chat.py`. The `messages` variable is used in various methods within the `ChatGPT` class, such as `format_for_anthropic`, `from_system_message_content`, `select_message_from_message_key`, `delete_messages_from_chat`, `get_message_content_from_message_key`, `update_message_content_from_message_key`, `chat`, and `call_openai`.

The `ChatGPT` class is used in several other files, including `sweepai/core/documentation_searcher.py`, `sweepai/core/code_repair.py`, `sweepai/core/context_pruning.py`, `sweepai/core/edit_chunk.py`, `sweepai/core/post_merge.py`, `sweepai/core/gha_extraction.py`, `sweepai/core/sweep_bot.py`, `sweepai/core/external_searcher.py`, `sweepai/core/slow_mode_expand.py`, and `tests/test_naive_chunker.py`.

Therefore, these files might also need to be updated to accommodate the refactoring of the `messages` variable.
</symbol_analysis>

<relevant_symbols_to_files>
Message:sweepai/core/entities.py
ChatGPT:sweepai/core/chat.py
ChatGPT:sweepai/core/documentation_searcher.py
ChatGPT:sweepai/core/code_repair.py
ChatGPT:sweepai/core/context_pruning.py
ChatGPT:sweepai/core/edit_chunk.py
ChatGPT:sweepai/core/post_merge.py
ChatGPT:sweepai/core/gha_extraction.py
ChatGPT:sweepai/core/sweep_bot.py
ChatGPT:sweepai/core/external_searcher.py
ChatGPT:sweepai/core/slow_mode_expand.py
ChatGPT:tests/test_naive_chunker.py
</relevant_symbols_to_files>"""

    symbols_to_files = """\
Message defined in sweepai/core/entities.py
ChatGPT used in sweepai/core/documentation_searcher.py
ChatGPT used in sweepai/core/code_repair.py
ChatGPT used in sweepai/core/context_pruning.py
ChatGPT used in sweepai/core/edit_chunk.py
ChatGPT used in sweepai/core/post_merge.py
ChatGPT used in sweepai/core/gha_extraction.py
ChatGPT used in sweepai/core/sweep_bot.py
ChatGPT used in sweepai/core/external_searcher.py
ChatGPT used in sweepai/core/slow_mode_expand.py
ChatGPT used in tests/test_naive_chunker.py
"""
    relevant_symbols_and_files = RelevantSymbolsAndFiles.from_string(
        response, symbols_to_files
    )
    assert relevant_symbols_and_files.relevant_files_to_symbols == {
        "sweepai/core/entities.py": ["Message"],
        "sweepai/core/chat.py": ["ChatGPT"],
        "sweepai/core/documentation_searcher.py": ["ChatGPT"],
        "sweepai/core/code_repair.py": ["ChatGPT"],
        "sweepai/core/context_pruning.py": ["ChatGPT"],
        "sweepai/core/edit_chunk.py": ["ChatGPT"],
        "sweepai/core/post_merge.py": ["ChatGPT"],
        "sweepai/core/gha_extraction.py": ["ChatGPT"],
        "sweepai/core/sweep_bot.py": ["ChatGPT"],
        "sweepai/core/external_searcher.py": ["ChatGPT"],
        "sweepai/core/slow_mode_expand.py": ["ChatGPT"],
        "tests/test_naive_chunker.py": ["ChatGPT"],
    }
