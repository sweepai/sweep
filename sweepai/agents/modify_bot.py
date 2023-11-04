import copy
import re
import uuid
from dataclasses import dataclass

from sweepai.agents.complete_code import ExtractLeftoverComments
from sweepai.agents.graph_child import extract_python_span
from sweepai.agents.prune_modify_snippets import PruneModifySnippets
from sweepai.config.server import DEBUG
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import FileChangeRequest, Message, Snippet, UnneededEditError
from sweepai.core.prompts import dont_use_chunking_message, use_chunking_message
from sweepai.core.update_prompts import (
    update_snippets_prompt,
    update_snippets_prompt_test,
    update_snippets_system_prompt,
    update_snippets_system_prompt_python,
)
from sweepai.utils.diff import generate_diff, sliding_window_replacement
from sweepai.utils.utils import chunk_code

fetch_snippets_system_prompt = """You are a masterful engineer. Your job is to extract the original sections from the code that should be modified.

Extract the smallest spans that let you handle the request by adding sections of sections_to_modify containing the code you want to modify. Use this for implementing or changing functionality.

<analysis_and_identification file="file_path">
Identify all changes that need to be made to the file.
Check the diff to make sure the changes have not previously been completed in this file.
In a list, identify all code sections that should receive these changes and all locations code should be added. These sections will go into the sections_to_modify block.
</analysis_and_identification>

<sections_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
...
</sections_to_modify>"""

fetch_snippets_prompt = """# Code
File path: {file_path}
<sections>
```
{code}
```
</sections>
{changes_made}
# Request
{request}

# Instructions
{chunking_message}

# Format
<analysis_and_identification file="file_path">
Identify all changes that need to be made to the file.
In a list, identify all code sections that should receive these changes and all locations code should be added. These sections will go into the sections_to_modify block.
</analysis_and_identification>

<sections_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
...
</sections_to_modify>"""

fetch_snippets_prompt_with_diff = """# Code
File path: {file_path}
<sections>
```
{code}
```
</sections>
{changes_made}
# Request
{request}

# Instructions
{chunking_message}

# Format
<analysis_and_identification file="file_path">
Identify all changes that need to be made to the file.
Check the diff to make sure the changes have not previously been completed in this file.
In a list, identify all code sections that should receive these changes and all locations code should be added. These sections will go into the sections_to_modify block.
</analysis_and_identification>

<sections_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
<section_to_modify reason="justification for modifying this entity">
SECTION_ID
</section_to_modify>
...
</sections_to_modify>"""

plan_snippets_system_prompt = """\
You are a brilliant and meticulous engineer assigned to plan code changes to complete the user's request.

You will plan code changes to solve the user's problems. You have the utmost care for the plans you write, so you do not make mistakes and you fully implement every function and class. Take into account the current repository's language, code style, and dependencies.

You will be given the old_file and potentially relevant snippets to edit. You do not necessarily have to edit all the snippets.

Respond in the following format:

<snippets_and_plan_analysis file="file_path">
Describe what should be changed to the snippets from the old_file to complete the request.
Then, for each snippet, describe in natural language in a list the changes needed, with references to the lines that should be changed and what to change it to.
Maximize information density and conciseness but be detailed.
</snippets_and_plan_analysis>"""

plan_snippets_prompt = """# Code
File path: {file_path}
<old_code>
```
{code}
```
</old_code>
{changes_made}
# Request
{request}

<snippets_to_update>
{snippets}
</snippets_to_update>

# Instructions
Describe all changes that should be made.

Respond in the following format:

<snippets_and_plan_analysis file="file_path">
Describe what should be changed to the snippets from the old_file to complete the request.
Then, for each snippet, describe in natural language in a list the changes needed, with references to the lines that should be changed and what to change it to.
Maximize information density and conciseness but be detailed.
</snippets_and_plan_analysis>"""


def get_last_import_line(code: str, max_: int = 150) -> int:
    lines = code.split("\n")
    for i, line in enumerate(reversed(lines)):
        if line.startswith("import ") or line.startswith("from "):
            return min(len(lines) - i - 1, max_)
    return -1


@dataclass
class SnippetToModify:
    snippet: Snippet
    reason: str


@dataclass
class MatchToModify:
    start: int
    end: int
    reason: str


def strip_backticks(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s[s.find("\n") :]
    if s.endswith("```"):
        s = s[: s.rfind("\n")]
    s = s.strip("\n")
    if s == '""':
        return ""
    return s


def int_to_excel_col(n):
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def excel_col_to_int(s):
    result = 0
    for char in s:
        result = result * 26 + (ord(char) - 64)
    return result - 1


class ModifyBot:
    def __init__(
        self,
        additional_messages: list[Message] = [],
        chat_logger=None,
        parent_bot: ChatGPT = None,
        old_file_contents: str = "",
        current_file_diff: str = "",
        **kwargs,
    ):
        self.fetch_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            fetch_snippets_system_prompt, chat_logger=chat_logger, **kwargs
        )
        self.fetch_snippets_bot.messages.extend(additional_messages)
        self.update_snippets_bot: ChatGPT = ChatGPT.from_system_message_string(
            update_snippets_system_prompt, chat_logger=chat_logger, **kwargs
        )
        self.update_snippets_bot.messages.extend(additional_messages)
        self.parent_bot = parent_bot

        self.extract_leftover_comments_bot: ExtractLeftoverComments = (
            ExtractLeftoverComments(chat_logger=chat_logger, **kwargs)
        )
        self.extract_leftover_comments_bot.messages.extend(additional_messages)
        self.prune_modify_snippets_bot: PruneModifySnippets = PruneModifySnippets(
            chat_logger=chat_logger, **kwargs
        )
        self.prune_modify_snippets_bot.messages.extend(additional_messages)
        self.chat_logger = chat_logger
        self.additional_messages = additional_messages
        self.old_file_contents = old_file_contents
        self.current_file_diff = current_file_diff
        self.additional_diffs = ""

    def get_diffs_message(self, file_contents: str):
        if self.current_file_diff == "" and self.old_file_contents == file_contents:
            return self.additional_diffs
        elif self.current_file_diff == "":
            diff = generate_diff(self.old_file_contents, file_contents)
        elif self.old_file_contents == file_contents:
            diff = self.current_file_diff
        else:
            diff = (
                self.old_file_contents
                + "\n...\n"
                + generate_diff(self.old_file_contents, file_contents)
            )
        diff += self.additional_diffs
        diff = diff.strip("\n")
        return f"\n# Changes Made\nHere are changes we already made to this file:\n<diff>\n{diff}\n</diff>\n"

    def try_update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        (
            snippet_queries,
            extraction_terms,
            analysis_and_identification,
        ) = self.get_snippets_to_modify(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            chunking=chunking,
        )

        new_file, leftover_comments = self.update_file(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            snippet_queries=snippet_queries,
            extraction_terms=extraction_terms,
            chunking=chunking,
            analysis_and_identification=analysis_and_identification,
        )
        for _ in range(3):
            if leftover_comments and not DEBUG:
                joined_comments = "\n".join(leftover_comments)
                new_file_change_request = copy.deepcopy(file_change_request)
                new_file_change_request.new_content = new_file
                new_file_change_request.id_ = str(uuid.uuid4())
                new_file_change_request.instructions = f"Address all of the unfinished code changes here: \n{joined_comments}"
                self.fetch_snippets_bot.messages = self.fetch_snippets_bot.messages[:-2]
                self.prune_modify_snippets_bot.messages = (
                    self.prune_modify_snippets_bot.messages[:-2]
                )
                (
                    snippet_queries,
                    extraction_terms,
                    analysis_and_identification,
                ) = self.get_snippets_to_modify(
                    file_path=file_path,
                    file_contents=new_file,
                    file_change_request=new_file_change_request,
                    chunking=chunking,
                )
                self.update_snippets_bot.messages = self.update_snippets_bot.messages[
                    :-2
                ]
                new_file, leftover_comments = self.update_file(
                    file_path=file_path,
                    file_contents=new_file,
                    file_change_request=new_file_change_request,
                    snippet_queries=snippet_queries,
                    extraction_terms=extraction_terms,
                    chunking=chunking,
                    analysis_and_identification=analysis_and_identification,
                )
        return new_file

    def get_snippets_to_modify(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        diffs_message = self.get_diffs_message(file_contents)
        fetch_prompt = (
            fetch_snippets_prompt_with_diff if diffs_message else fetch_snippets_prompt
        )
        original_snippets = chunk_code(file_contents, file_path, 700, 200)
        file_contents_lines = file_contents.split("\n")
        chunks = [
            "\n".join(file_contents_lines[snippet.start : snippet.end + 1])
            for snippet in original_snippets
        ]
        code_sections = []
        for i, chunk in enumerate(chunks):
            idx = int_to_excel_col(i + 1)
            code_sections.append(f'<section id="{idx}">\n{chunk}\n</section>')

        fetch_snippets_response = self.fetch_snippets_bot.chat(
            fetch_prompt.format(
                code="\n".join(code_sections),
                changes_made=self.get_diffs_message(file_contents),
                file_path=file_path,
                request=file_change_request.instructions,
                chunking_message=use_chunking_message
                if chunking
                else dont_use_chunking_message,
            )
        )
        analysis_and_identification_pattern = r"<analysis_and_identification.*?>\n(?P<code>.*)\n</analysis_and_identification>"
        analysis_and_identification_match = re.search(
            analysis_and_identification_pattern, fetch_snippets_response, re.DOTALL
        )
        analysis_and_identifications_str = (
            analysis_and_identification_match.group("code").strip()
            if analysis_and_identification_match
            else ""
        )

        extraction_terms = []
        extraction_term_pattern = (
            r"<extraction_terms.*?>\n(?P<extraction_term>.*?)\n</extraction_terms>"
        )
        for extraction_term in re.findall(
            extraction_term_pattern, fetch_snippets_response, re.DOTALL
        ):
            for term in extraction_term.split("\n"):
                term = term.strip()
                if term:
                    extraction_terms.append(term)
        snippet_queries = []
        snippets_query_pattern = r"<section_to_modify.*?(reason=\"(?P<reason>.*?)\")?>\n(?P<section>.*?)\n</section_to_modify>"
        for match_ in re.finditer(
            snippets_query_pattern, fetch_snippets_response, re.DOTALL
        ):
            section = match_.group("section").strip()
            snippet = original_snippets[excel_col_to_int(section)]
            reason = match_.group("reason").strip()
            snippet_queries.append(
                SnippetToModify(reason=reason or "", snippet=snippet)
            )

        if len(snippet_queries) == 0:
            raise UnneededEditError("No snippets found in file")
        return snippet_queries, extraction_terms, analysis_and_identifications_str

    def update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        snippet_queries: list[SnippetToModify],
        extraction_terms: list[str],
        chunking: bool = False,
        analysis_and_identification: str = "",
    ):
        is_python_file = file_path.strip().endswith(".py")

        chunk_code(file_contents, file_path, 700, 200)

        best_matches = []
        for snippet_to_modify in snippet_queries:
            best_matches.append(
                MatchToModify(
                    start=snippet_to_modify.snippet.start,
                    end=snippet_to_modify.snippet.end + 1,
                    reason=snippet_to_modify.reason,
                )
            )

        best_matches.sort(key=lambda x: x.start + x.end * 0.00001)

        def fuse_matches(a: MatchToModify, b: MatchToModify) -> MatchToModify:
            reason = (
                f"{a.reason} & {b.reason}" if b.reason not in a.reason else a.reason
            )
            if b.reason == "Import statements":
                reason = a.reason
            elif a.reason == "Import statements":
                reason = b.reason
            elif b.reason.startswith("Mentioned") or b.reason.endswith("function call"):
                reason = a.reason
            elif a.reason.startswith("Mentioned") or a.reason.endswith("function call"):
                reason = b.reason
            return MatchToModify(
                start=min(a.start, b.start), end=max(a.end, b.end), reason=reason
            )

        deduped_matches = best_matches

        selected_snippets: list[tuple[str, str]] = []
        file_contents_lines = file_contents.split("\n")
        for match_ in deduped_matches:
            current_contents = "\n".join(file_contents_lines[match_.start : match_.end])
            selected_snippets.append((match_.reason, current_contents))

        update_snippets_code = file_contents
        if file_change_request.entity:
            update_snippets_code = extract_python_span(
                file_contents, [file_change_request.entity]
            ).content

        if len(selected_snippets) > 1:
            indices_to_keep = self.prune_modify_snippets_bot.prune_modify_snippets(
                snippets="\n\n".join(
                    [
                        f'<snippet index="{i}" reason="{reason}">\n{snippet}\n</snippet>'
                        for i, (reason, snippet) in enumerate(selected_snippets)
                    ]
                ),
                file_path=file_path,
                changes_made=self.get_diffs_message(file_contents),
                old_code=update_snippets_code,
                request=file_change_request.instructions
                + "\n"
                + analysis_and_identification,
            )
        else:
            indices_to_keep = [0]

        if len(indices_to_keep) == 0:
            raise UnneededEditError("No snippets selected")

        pruned_snippets = []
        for idx, snippet in enumerate(selected_snippets):
            if idx in indices_to_keep:
                pruned_snippets.append(snippet)
        selected_snippets = pruned_snippets

        if is_python_file:
            self.update_snippets_bot.messages[
                0
            ].content = update_snippets_system_prompt_python

        if file_change_request.failed_sandbox_test:
            update_prompt = update_snippets_prompt_test
        else:
            update_prompt = update_snippets_prompt
        update_snippets_response = self.update_snippets_bot.chat(
            update_prompt.format(
                code=update_snippets_code,
                file_path=file_path,
                snippets="\n\n".join(
                    [
                        f'<snippet index="{i}" reason="{reason}">\n{snippet}\n</snippet>'
                        for i, (reason, snippet) in enumerate(selected_snippets)
                    ]
                )
                + "\n"
                + analysis_and_identification,
                request=file_change_request.instructions,
                n=len(selected_snippets),
                changes_made=self.get_diffs_message(file_contents),
            )
        )
        updated_snippets: dict[int, str] = {}
        updated_pattern = r"<<<<<<<\s+REPLACE\s+\(index=(?P<index>\d+)\)(?P<original_code>.*?)=======(?P<updated_code>.*?)>>>>>>>"
        append_pattern = (
            r"<<<<<<<\s+APPEND\s+\(index=(?P<index>\d+)\)(?P<updated_code>.*?)>>>>>>>"
        )

        if (
            len(list(re.finditer(updated_pattern, update_snippets_response, re.DOTALL)))
            == 0
            and len(
                list(re.finditer(append_pattern, update_snippets_response, re.DOTALL))
            )
            == 0
        ):
            raise UnneededEditError("No snippets edited")

        for match_ in re.finditer(updated_pattern, update_snippets_response, re.DOTALL):
            index = int(match_.group("index"))
            original_code = match_.group("original_code").strip("\n")
            updated_code = match_.group("updated_code").strip("\n")

            _reason, current_contents = selected_snippets[index]
            if index not in updated_snippets:
                updated_snippets[index] = current_contents
            else:
                current_contents = updated_snippets[index]
            updated_snippets[index] = "\n".join(
                sliding_window_replacement(
                    original=current_contents.splitlines(),
                    search=original_code.splitlines(),
                    replace=updated_code.splitlines(),
                )[0]
            )

        for match_ in re.finditer(append_pattern, update_snippets_response, re.DOTALL):
            index = int(match_.group("index"))
            updated_code = match_.group("updated_code").strip("\n")

            _reason, current_contents = selected_snippets[index]
            if index not in updated_snippets:
                updated_snippets[index] = current_contents
            else:
                current_contents = updated_snippets[index]
            updated_snippets[index] = current_contents + "\n" + updated_code

        result = file_contents
        new_code = []
        for idx, (_reason, search) in enumerate(selected_snippets):
            if idx not in updated_snippets:
                continue
            replace = updated_snippets[idx]
            result = "\n".join(
                sliding_window_replacement(
                    original=result.splitlines(),
                    search=search.splitlines(),
                    replace=replace.splitlines(),
                )[0]
            )
            new_code.append(replace)

        ending_newlines = len(file_contents) - len(file_contents.rstrip("\n"))
        result = result.rstrip("\n") + "\n" * ending_newlines

        new_code = "\n".join(new_code)
        leftover_comments = (
            (
                self.extract_leftover_comments_bot.extract_leftover_comments(
                    new_code,
                    file_path,
                    file_change_request.instructions,
                )
            )
            if not DEBUG
            else []
        )

        return result, leftover_comments


if __name__ == "__main__":
    response = """
```python
```"""
    stripped = strip_backticks(response)
    print(stripped)
