from dataclasses import dataclass
import re
from fuzzywuzzy import fuzz
from logn import logger

from tqdm import tqdm


def score_line(str1: str, str2: str) -> float:
    if str1 == str2:
        return 100

    if str1.lstrip() == str2.lstrip():
        whitespace_ratio = abs(len(str1) - len(str2)) / (len(str1) + len(str2))
        score = 90 - whitespace_ratio * 10
        return max(score, 0)

    if str1.strip() == str2.strip():
        whitespace_ratio = abs(len(str1) - len(str2)) / (len(str1) + len(str2))
        score = 80 - whitespace_ratio * 10
        return max(score, 0)

    levenshtein_ratio = fuzz.ratio(str1, str2)

    score = 70 * (levenshtein_ratio / 100)
    return max(score, 0)


def match_without_whitespace(str1: str, str2: str) -> bool:
    return str1.strip() == str2.strip()


def line_cost(line: str) -> float:
    if line.strip() == "":
        return 50
    if line.strip().startswith("#") or line.strip().startswith("//"):
        return 50 + len(line) / (len(line) + 1) * 30
    return len(line) / (len(line) + 1) * 100


def score_multiline(query: list[str], target: list[str]) -> float:
    # TODO: add weighting on first and last lines

    q, t = 0, 0  # indices for query and target
    scores: list[tuple[float, float]] = []
    skipped_comments = 0
    def get_weight(q: int) -> float:
        # Prefers lines at beginning and end of query
        # Sequence: 1, 2/3, 1/2, 2/5...
        index = min(q, len(query) - q)
        return 100 / (index / 2 + 1)
    while q < len(query) and t < len(target):
        q_line = query[q]
        t_line = target[t]
        weight = get_weight(q)

        if match_without_whitespace(q_line, t_line):
            # Case 1: lines match
            scores.append((score_line(q_line, t_line), weight))
            q += 1
            t += 1
        elif "..." in q_line:
            # Case 3: ellipsis wildcard
            lines_matched = 1
            t += 1
            if q + 1 == len(query):
                scores.append((100 - (len(target) - t), weight))
                q += 1
                t = len(target)
                break
            max_score = 0
            for i in range(t, len(target)):
                # TODO: use radix to optimize
                score, weight = score_multiline(query[q + 1 :], target[i:]), (
                    100 - (i - t) / len(target) * 10
                )
                new_scores = scores + [(score, weight)]
                total_score = sum(
                    [value * weight for value, weight in new_scores]
                ) / sum([weight for _, weight in new_scores])
                max_score = max(max_score, total_score)
            return max_score
        elif (
            t_line.strip() == ""
            or t_line.strip().startswith("#")
            or t_line.strip().startswith("//")
        ):
            # Case 2: skipped comment
            skipped_comments += 1
            t += 1
            scores.append((90, weight))
        else:
            break

    if q < len(query):
        scores.extend(
            (100 - line_cost(line), get_weight(index))
            for index, line in enumerate(query[q:])
        )
    if t < len(target):
        scores.extend(
            (100 - line_cost(line), 100) for index, line in enumerate(target[t:])
        )

    final_score = (
        sum([value * weight for value, weight in scores])
        / sum([weight for _, weight in scores])
        if scores
        else 0
    )
    final_score *= 1 - 0.05 * skipped_comments

    return final_score


@dataclass
class Match:
    start: int
    end: int
    score: float
    indent: str = ""

    def __gt__(self, other):
        return self.score > other.score


def get_indent_type(content: str):
    two_spaces = len(re.findall(r"\n {2}[^ ]", content))
    four_spaces = len(re.findall(r"\n {4}[^ ]", content))

    return "  " if two_spaces > four_spaces else "    "


def get_max_indent(content: str, indent_type: str):
    return max(len(line) - len(line.lstrip()) for line in content.split("\n")) // len(
        indent_type
    )


def find_best_match(query: str, code_file: str):
    best_match = Match(-1, -1, 0)

    code_file_lines = code_file.split("\n")
    query_lines = query.split("\n")
    if len(query_lines) > 0 and query_lines[-1].strip() == "...":
        query_lines = query_lines[:-1]
    indent = get_indent_type(code_file)
    max_indents = get_max_indent(code_file, indent)

    top_matches = []

    if len(query_lines) == 1:
        for i, line in enumerate(code_file_lines):
            score = score_line(line, query_lines[0])
            if score > best_match.score:
                best_match = Match(i, i + 1, score)
        return best_match

    for num_indents in range(0, min(max_indents + 1, 20)):
        # Optimize later by using radix
        indented_query_lines = [indent * num_indents + line for line in query_lines]
        # for line in code_file_lines:
        #     # print(line)
        #     print(score_line(line, indented_query_lines[0]))

        start_indices = [
            i
            for i, line in enumerate(code_file_lines)
            if score_line(line, indented_query_lines[0]) > 50
        ]
        start_indices = start_indices or [
            i
            for i in start_indices
            if score_multiline(indented_query_lines[:2], code_file_lines[i : i + 2])
            > 50
        ]

        if not start_indices:
            start_pairs = [
                (i, score_line(line, indented_query_lines[0]))
                for i, line in enumerate(code_file_lines)
            ]
            start_pairs.sort(key=lambda x: x[1], reverse=True)
            start_pairs = start_pairs[: min(20, len(start_pairs) // 10)]
            start_indices = sorted([i for i, _ in start_pairs])

        for i in tqdm(start_indices):
            for j in range(
                i + len(indented_query_lines),
                min(len(code_file_lines) + 1, i + 2 * len(indented_query_lines) + 100),
            ):
                candidate = code_file_lines[i:j]
                score = score_multiline(indented_query_lines, candidate) * (
                    1 - num_indents * 0.01
                )
                current_match = Match(i, j, score, indent * num_indents)

                top_matches.append(current_match)

                if score > best_match.score:
                    best_match = current_match

    unique_top_matches: list[Match] = []
    print(unique_top_matches)
    unique_spans = set()
    for top_match in sorted(top_matches, reverse=True):
        if (top_match.start, top_match.end) not in unique_spans:
            unique_top_matches.append(top_match)
            unique_spans.add((top_match.start, top_match.end))
    for top_match in unique_top_matches[:5]:
        logger.print(top_match)

    # Todo: on_comment file comments able to modify multiple files
    return unique_top_matches[0] if unique_top_matches else Match(-1, -1, 0)

if __name__ == "__main__":
    code_file = """from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import field
import traceback
import re
import requests
from typing import Generator, Any, Dict, List, Tuple
from logn import logger

from github.ContentFile import ContentFile
from github.GithubException import GithubException, UnknownObjectException
from github.Repository import Repository
from github.Commit import Commit
from pydantic import BaseModel
from sweepai.agents.graph_child import GraphChildBot, GraphContextAndPlan
from sweepai.agents.graph_parent import GraphParentBot

from sweepai.core.chat import ChatGPT
from sweepai.core.edit_chunk import EditBot
from sweepai.core.entities import (
    FileCreation,
    ProposedIssue,
    FileChangeRequest,
    PullRequest,
    RegexMatchError,
    SandboxResponse,
    SectionRewrite,
    Snippet,
    NoFilesException,
    Message,
    MaxTokensExceeded,
)

# from sandbox.modal_sandbox import SandboxError  # pylint: disable=E0401
from sweepai.core.prompts import (
    files_to_change_prompt,
    subissues_prompt,
    pull_request_prompt,
    create_file_prompt,
    modify_file_prompt_3,
    modify_file_system_message,
    snippet_replacement,
    chunking_prompt,
    RECREATE_LINE_LENGTH,
    modify_recreate_file_system_message,
    modify_recreate_file_prompt_3,
    rewrite_file_prompt,
    rewrite_file_system_prompt,
    snippet_replacement_system_message,
    fetch_snippets_system_prompt,
    fetch_snippets_prompt,
    update_snippets_system_prompt,
    update_snippets_prompt,
    python_files_to_change_prompt,
)
from sweepai.config.client import SweepConfig, get_blocked_dirs, get_branch_name_config
from sweepai.config.server import DB_MODAL_INST_NAME, SANDBOX_URL, SECONDARY_MODEL
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.diff import (
    format_contents,
    generate_diff,
    generate_new_file_from_patch,
    is_markdown,
    get_matches,
    sliding_window_replacement,
)

from sweepai.utils.graph import Graph
from sweepai.utils.prompt_constructor import PythonHumanMessagePrompt
from sweepai.utils.search_and_replace import Match, find_best_match
from sweepai.utils.utils import chunk_code

USING_DIFF = True

BOT_ANALYSIS_SUMMARY = "bot_analysis_summary"


def strip_backticks(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s[s.find("\n") :]
    if s.endswith("```"):
        s = s[: s.rfind("\n")]
    return s.strip("\n")


def remove_line_numbers(s: str) -> str:
    # Check if more than 50% of lines have line numbers
    # Remove line numbers with spaces after (e.g. "1: {code}")
    if len(re.findall(r"\d+?: ", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?: ", "", s, flags=re.MULTILINE)

    # Remove line numbers with no space after (e.g. "112:{code}")
    if len(re.findall(r"\d+?:", s)) > len(s.split("\n")) / 2:
        return re.sub(r"\d+?:", "", s, flags=re.MULTILINE)
    return s


def match_indent(generated: str, original: str) -> str:
    indent_type = "\t" if "\t" in original[:5] else " "
    generated_indents = len(generated) - len(generated.lstrip())
    target_indents = len(original) - len(original.lstrip())
    diff_indents = target_indents - generated_indents
    if diff_indents > 0:
        generated = indent_type * diff_indents + generated.replace(
            "\n", "\n" + indent_type * diff_indents
        )
    return generated


class CodeGenBot(ChatGPT):
    def summarize_snippets(self):
        # Custom system message for snippet replacement
        old_msg = self.messages[0].content
        self.messages[0].content = snippet_replacement_system_message

        snippet_summarization = self.chat(
            snippet_replacement,
            message_key="snippet_summarization",
        )  # maybe add relevant info

        self.messages[0].content = old_msg

        contextual_thought_match = re.search(
            "<contextual_thoughts>(?P<thoughts>.*)</contextual_thoughts>",
            snippet_summarization,
            re.DOTALL,
        )
        contextual_thought: str = (
            contextual_thought_match.group("thoughts").strip()
            if contextual_thought_match
            else ""
        )
        relevant_snippets_match = re.search(
            "<relevant_snippets>(?P<snippets>.*)</relevant_snippets>",
            snippet_summarization,
            re.DOTALL,
        )
        relevant_snippets: str = (
            relevant_snippets_match.group("snippets").strip()
            if relevant_snippets_match
            else ""
        )

        try:
            snippets: Snippet = []
            for raw_snippet in relevant_snippets.split("\n"):
                if ":" not in raw_snippet:
                    logger.warning(
                        f"Error in summarize_snippets: {raw_snippet}. Likely failed to"
                        " parse"
                    )
                file_path, lines = raw_snippet.split(":", 1)
                if "-" not in lines:
                    logger.warning(
                        f"Error in summarize_snippets: {raw_snippet}. Likely failed to"
                        " parse"
                    )
                start, end = lines.split("-", 1)
                start = int(start)
                end = int(end) - 1
                end = min(end, start + 200)

                snippet = Snippet(file_path=file_path, start=start, end=end, content="")
                snippets.append(snippet)

            self.populate_snippets(snippets)
            snippets = [snippet.expand() for snippet in snippets]
            snippets_text = "\n".join([snippet.xml for snippet in snippets])
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.warning(f"Error in summarize_snippets: {e}. Likely failed to parse")
            snippets_text = self.get_message_content_from_message_key(
                "relevant_snippets"
            )

        # Remove line numbers (1:line) from snippets
        snippets_text = re.sub(r"^\d+?:", "", snippets_text, flags=re.MULTILINE)

        msg_content = (
            "Contextual thoughts: \n"
            + contextual_thought
            + "\n\nRelevant snippets:\n\n"
            + snippets_text
            + "\n\n"
        )

        self.delete_messages_from_chat("relevant_snippets")
        self.delete_messages_from_chat("relevant_directories")
        self.delete_messages_from_chat("relevant_tree")
        self.delete_messages_from_chat("files_to_change", delete_assistant=False)
        self.delete_messages_from_chat("snippet_summarization")

        msg = Message(content=msg_content, role="assistant", key=BOT_ANALYSIS_SUMMARY)
        self.messages.insert(-2, msg)

    def generate_subissues(self, retries: int = 3):
        subissues: list[ProposedIssue] = []
        for count in range(retries):
            try:
                logger.info(f"Generating for the {count}th time...")
                files_to_change_response = self.chat(
                    subissues_prompt, message_key="subissues"
                )  # Dedup files to change here
                subissues = []
                for re_match in re.finditer(
                    ProposedIssue._regex, files_to_change_response, re.DOTALL
                ):
                    subissues.append(ProposedIssue.from_string(re_match.group(0)))
                if subissues:
                    return subissues
            except RegexMatchError:
                logger.warning("Failed to parse! Retrying...")
                self.delete_messages_from_chat("files_to_change")
                continue
        raise NoFilesException()

    def get_files_to_change(
        self, retries=1, pr_diffs: str | None = None
    ) -> tuple[list[FileChangeRequest], str]:
        file_change_requests: list[FileChangeRequest] = []
        # Todo: put retries into a constants file
        # also, this retries multiple times as the calls for this function are in a for loop
        try:
            is_python_issue = (
                sum(
                    [
                        not file_path.endswith(".py")
                        for file_path in self.human_message.get_file_paths()
                    ]
                )
                < 2
            )
            logger.info(f"IS PYTHON ISSUE: {is_python_issue}")
            python_issue_worked = True
            if is_python_issue:
                graph = Graph.from_folder(folder_path=self.cloned_repo.cache_dir)
                graph_parent_bot = GraphParentBot(chat_logger=self.chat_logger)
                if pr_diffs is not None:
                    self.delete_messages_from_chat("pr_diffs")
                    graph_parent_bot.messages.insert(
                        1, Message(role="user", content=pr_diffs, key="pr_diffs")
                    )

                issue_metadata = self.human_message.get_issue_metadata()
                relevant_snippets = self.human_message.render_snippets()
                symbols_to_files = graph.paths_to_first_degree_entities(
                    self.human_message.get_file_paths()
                )
                if len(symbols_to_files) <= 1:
                    python_issue_worked = False

                if python_issue_worked:
                    (
                        relevant_files_to_symbols,
                        relevant_symbols_string,
                    ) = graph_parent_bot.relevant_files_to_symbols(
                        issue_metadata, relevant_snippets, symbols_to_files
                    )

                    file_paths_to_contents = {
                        file_path: self.cloned_repo.get_file_contents(file_path)
                        for file_path in relevant_files_to_symbols.keys()
                    }

                    # Create plan for relevant snippets first
                    human_message_snippet_paths = set(
                        s.file_path for s in self.human_message.snippets
                    )
                    non_human_message_snippet_paths = set()
                    for file_path in relevant_files_to_symbols.keys():
                        non_human_message_snippet_paths.add(
                            file_path
                        )  # TODO (luke) use trimmed context of initial files in this step instead of self.human_message.render_snippet_array(other_snippets)
                    plans: list[GraphContextAndPlan] = []
                    for file_path in (
                        human_message_snippet_paths | non_human_message_snippet_paths
                    ):
                        other_snippets = [
                            snippet
                            for snippet in self.human_message.snippets
                            if snippet.file_path != file_path
                            and file_path
                            in human_message_snippet_paths  # <- trim these once the human messages are parsed
                        ]
                        if file_path in human_message_snippet_paths:
                            snippet = next(
                                snippet
                                for snippet in self.human_message.snippets
                                if snippet.file_path == file_path
                            )
                        else:
                            snippet = Snippet(
                                file_path=file_path,
                                start=0,
                                end=0,
                                content=file_paths_to_contents[file_path],
                            )
                        relevant_symbol_list = []
                        for v in relevant_files_to_symbols.values():
                            relevant_symbol_list.extend(v)
                        plan_bot = GraphChildBot(chat_logger=self.chat_logger)
                        plan = plan_bot.code_plan_extraction(
                            code=snippet.content,
                            file_path=file_path,
                            entities=relevant_symbol_list,
                            issue_metadata=issue_metadata,
                            previous_snippets=self.human_message.render_snippet_array(
                                other_snippets
                            ),
                            all_symbols_and_files=relevant_symbols_string,
                        )
                        if plan.relevant_new_snippet:
                            plans.append(plan)
                    file_path_set = set()
                    deduped_plans = []
                    for plan in plans:
                        if plan.file_path not in file_path_set:
                            file_path_set.add(plan.file_path)
                            deduped_plans.append(plan)
                        else:
                            logger.info(f"Duplicate plan for {plan.file_path}")
                    plans = deduped_plans

                    # topologically sort the plans so that we can apply them in order
                    file_paths = [plan.file_path for plan in plans]
                    sorted_files = graph.topological_sort(file_paths)
                    sorted_plans = []
                    for file_path in sorted_files:
                        sorted_plans.append(
                            next(
                                plan for plan in plans if plan.file_path == file_path
                            )  # TODO: use a dict instead
                        )
                    plans = sorted_plans

                    relevant_snippets = []
                    for plan in plans:
                        relevant_snippets.extend(plan.relevant_new_snippet)

                    python_human_message = PythonHumanMessagePrompt(
                        repo_name=self.human_message.repo_name,
                        issue_url=self.human_message.issue_url,
                        username=self.human_message.username,
                        title=self.human_message.title,
                        summary=self.human_message.summary,
                        snippets=relevant_snippets,
                        tree=self.human_message.tree,
                        repo_description=self.human_message.repo_description,
                    )
                    prompt_message_dicts = python_human_message.construct_prompt()
                    new_messages = [self.messages[0]]
                    for message_dict in prompt_message_dicts:
                        new_messages.append(Message(**message_dict))
                    self.messages = new_messages
                    files_to_change_response = self.chat(
                    files_to_change_prompt, message_key="files_to_change"
                    )  # Dedup files to change here
                    file_change_requests = []
                    for re_match in re.finditer(
                        FileChangeRequest._regex, files_to_change_response, re.DOTALL
                    ):
                        file_change_requests.append(
                            FileChangeRequest.from_string(re_match.group(0))
                        )
                    

                    if file_change_requests:
                        return file_change_requests, files_to_change_response
            if not is_python_issue or not python_issue_worked:
                if pr_diffs is not None:
                    self.delete_messages_from_chat("pr_diffs")
                    self.messages.insert(
                        1, Message(role="user", content=pr_diffs, key="pr_diffs")
                    )

                files_to_change_response = self.chat(
                    files_to_change_prompt, message_key="files_to_change"
                )  # Dedup files to change here
            file_change_requests = []
            for re_match in re.finditer(
                FileChangeRequest._regex, files_to_change_response, re.DOTALL
            ):
                file_change_requests.append(
                    FileChangeRequest.from_string(re_match.group(0))
                )

            if file_change_requests:
                return file_change_requests, files_to_change_response
        except RegexMatchError as e:
            logger.print(e)
            logger.warning("Failed to parse! Retrying...")
            self.delete_messages_from_chat("files_to_change")
            self.delete_messages_from_chat("pr_diffs")

        raise NoFilesException()

    def generate_pull_request(self, retries=2) -> PullRequest:
        for count in range(retries):
            too_long = False
            try:
                logger.info(f"Generating for the {count}th time...")
                if (
                    too_long or count >= retries - 1
                ):  # if on last try, use gpt4-32k (improved context window)
                    pr_text_response = self.chat(
                        pull_request_prompt, message_key="pull_request"
                    )
                else:
                    pr_text_response = self.chat(
                        pull_request_prompt,
                        message_key="pull_request",
                        model=SECONDARY_MODEL,
                    )

                # Add triple quotes if not present
"""

    # Sample target snippet
    target = """
def get_files_to_change(
    self, retries=1, pr_diffs: str | None = None
) -> tuple[list[FileChangeRequest], str]:
    file_change_requests: list[FileChangeRequest] = []
    try:
        is_python_issue = (
            sum(
                [
                    not file_path.endswith(".py")
                    for file_path in self.human_message.get_file_paths()
                ]
            )
            < 2
        )
        logger.info(f"IS PYTHON ISSUE: {is_python_issue}")
        python_issue_worked = True
        if is_python_issue:
    """.strip("\n")

    _match = """
def get_files_to_change(
    self, retries=1, pr_diffs: str | None = None
) -> tuple[list[FileChangeRequest], str]:
    file_change_requests: list[FileChangeRequest] = []
    # Todo: put retries into a constants file
    # also, this retries multiple times as the calls for this function are in a for loop
    try:
        is_python_issue = (
            sum(
                [
                    not file_path.endswith(".py")
                    for file_path in self.human_message.get_file_paths()
                ]
            )
            < 2
        )
        logger.info(f"IS PYTHON ISSUE: {is_python_issue}")
        python_issue_worked = True
        if is_python_issue:
    """.strip("\n")

    print(score_multiline(target.split("\n"), _match.split("\n")))
    quit()

    # Find the best match
    best_span = find_best_match(target, code_file)
    best_code_snippet = "\n".join(code_file.split('\n')[best_span.start:best_span.end])
    print(f"Best code snippet:\n{best_code_snippet}")
    print(f"Best match line numbers: {best_span.start}-{best_span.end}")