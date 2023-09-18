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
        elif (
            t_line.strip() == ""
            and t_line.strip().startswith("#")
            or t_line.strip().startswith("//")
        ):
            # Case 2: skipped comment
            skipped_comments += 1
            q += 1
            t += 2
            scores.append((90, weight))
        elif "..." in q_line:
            # Case 3: ellipsis wildcard
            lines_matched = 1
            t += 1
            if q + 1 == len(query):
                scores.append((100 - (len(target) - t), weight))
                q += 1
                t = len(target)
                break
            while t < len(target) and not match_without_whitespace(
                query[q + 1], target[t]
            ):
                lines_matched += 1
                t += 1
            if t == len(target):
                break
            q += 1
            scores.append(((100 - lines_matched), weight))
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
        start_indices = [
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
    unique_spans = set()
    for top_match in sorted(top_matches, reverse=True):
        if (top_match.start, top_match.end) not in unique_spans:
            unique_top_matches.append(top_match)
            unique_spans.add((top_match.start, top_match.end))
    for top_match in unique_top_matches[:5]:
        logger.print(top_match)

    return unique_top_matches[0]


code_file = """
# Import libraries
import os
import sys

# Initialize
def initialize():
    print("Initializing...")
    x = 1
    y = 2
    print("Done!")

# Main function
def main():
    print("Hello, World!")
"""

# Sample target snippet
target = """
# Initialize
def initialize():
    ...
    print("Done!")
""".strip()

# query = """\
# foo()
# print("hello world")
# ...
# bar()\
# """

# target = """\
# foo()
# // this is a comment
# print("hello world")
# xyz()
# test()
# bar()\
# """

# query = """\
# foo()
# print("hello world")
# ...\
# """

# target = """\
# foo()
# // this is a comment
# print("hello world")
# xyz()
# test()\
# """

# query = """\
# # Initialize
# def initialize():
#     ...
#     print("Done!")\
# """

# target = """\
# # Initialize
# def initialize():
#     print("Initializing...")
#     x = 1
#     y = 2
#     print("Done!")
# \
# """

# print(score_multiline(query.split("\n"), target.split("\n")))

# Find the best match
# best_span = find_best_match(target, code_file)
# print(f"Best match line numbers: {best_span}")

# if __name__ == "__main__":
#     string1 = "hello world"
#     string2 = "hello   world!"

#     string1 = "     hello world"
#     string2 = "hello world"

# score = line_scoring(string1, string2)
#     print(f"Score: {score}%")
