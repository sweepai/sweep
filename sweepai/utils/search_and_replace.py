import re
from dataclasses import dataclass

from fuzzywuzzy import fuzz
from tqdm import tqdm

from logn import logger


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
    if len(query_lines) > 0 and query_lines[0].strip() == "...":
        query_lines = query_lines[1:]
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
    code_file = """\
    def try_update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        snippet_queries = self.get_snippets_to_modify(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            chunking=chunking,
        )

        new_file = self.update_file(
            file_path=file_path,
            file_contents=file_contents,
            file_change_request=file_change_request,
            snippet_queries=snippet_queries,
            chunking=chunking,
        )
        return new_file

    def get_snippets_to_modify(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        fetch_snippets_response = self.fetch_snippets_bot.chat(
            fetch_snippets_prompt.format(
                code=file_contents,
                file_path=file_path,
                request=file_change_request.instructions,
                chunking_prompt='\nThe request may not apply to this section of the code. If so, reply with "No changes needed"\n'
                if chunking
                else "",
            )
        )

        snippet_queries = []
        query_pattern = r"<snippet_to_modify.*?>(?P<code>.*?)</snippet_to_modify>"
        for code in re.findall(query_pattern, fetch_snippets_response, re.DOTALL):
            snippet_queries.append(strip_backticks(code))

        assert len(snippet_queries) > 0, "No snippets found in file"
        return snippet_queries

    def update_file(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        snippet_queries: list[str],
        chunking: bool = False,
    ):
        best_matches = []
        for query in snippet_queries:
            _match = find_best_match(query, file_contents)
            if _match.score > 50:
                best_matches.append(_match)

        if len(best_matches) == 0:
            raise UnneededEditError("No matches found in file")

        # Todo: check multiple files for matches using PR changed files

        best_matches.sort(key=lambda x: x.start + x.end * 0.001)

        def fuse_matches(a: Match, b: Match) -> Match:
            return Match(
                start=min(a.start, b.start),
                end=max(a.end, b.end),
                score=min(a.score, b.score),
            )
"""

    # Sample target snippet
    target = """
    def get_snippets_to_modify(
        self,
        file_path: str,
        file_contents: str,
        file_change_request: FileChangeRequest,
        chunking: bool = False,
    ):
        fetch_snippets_response = self.fetch_snippets_bot.chat(
            fetch_snippets_prompt.format(
                code=file_contents,
                file_path=file_path,
                request=file_change_request.instructions,
                chunking_prompt='\nThe request may not apply to this section of the code. If so, reply with "No changes needed"\n'
                if chunking
                else "",
            )
        )

        snippet_queries = []
        query_pattern = r"<snippet_to_modify.*?>(?P<code>.*?)</snippet_to_modify>"
        for code in re.findall(query_pattern, fetch_snippets_response, re.DOTALL):
            snippet_queries.append(strip_backticks(code))

        assert len(snippet_queries) > 0, "No snippets found in file"
        return snippet_queries
    """.strip(
        "\n"
    )

    # Find the best match
    best_span = find_best_match(target, code_file)
    best_code_snippet = "\n".join(
        code_file.split("\n")[best_span.start : best_span.end]
    )
    print(f"Best code snippet:\n{best_code_snippet}")
    print(f"Best match line numbers: {best_span.start}-{best_span.end}")
