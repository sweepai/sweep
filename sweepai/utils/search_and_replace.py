import re
from dataclasses import dataclass

from fuzzywuzzy import fuzz
from tqdm import tqdm

from sweepai.logn import logger


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
            # Radix optimization
            indices = [
                t + i
                for i, line in enumerate(target[t:])
                if match_without_whitespace(line, query[q + 1])
            ]
            if not indices:
                # logger.warning(f"Could not find whitespace match, using brute force")
                indices = range(t, len(target))
            for i in indices:
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
        indented_query_lines = [indent * num_indents + line for line in query_lines]

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
            start_pairs = start_pairs[: min(40, len(start_pairs) // 5)]
            start_indices = sorted([i for i, _ in start_pairs])

        for i in tqdm(
            start_indices,
            position=0,
            desc=f"Indent {num_indents}/{max_indents}",
            leave=False,
        ):
            end_indices = [
                j
                for j, line in enumerate(code_file_lines[i:], start=i)
                if score_line(line, indented_query_lines[-1]) > 50
            ]
            end_indices = end_indices or [
                j
                for j in end_indices
                if score_multiline(
                    indented_query_lines[-2:], code_file_lines[i + j - 1 : i + j + 1]
                )
                > 50
            ]  # sus code
            if not end_indices:
                end_pairs = [
                    (j, score_line(line, indented_query_lines[-1]))
                    for j, line in enumerate(code_file_lines[i:], start=i)
                ]
                end_pairs.sort(key=lambda x: x[1], reverse=True)
                end_pairs = end_pairs[: min(40, len(end_pairs) // 5)]
                end_indices = sorted([j for j, _ in end_pairs])

            for j in tqdm(
                end_indices, position=1, leave=False, desc=f"Starting line {i}"
            ):
                candidate = code_file_lines[i : j + 1]
                raw_score = score_multiline(indented_query_lines, candidate)

                score = raw_score * (1 - num_indents * 0.01)
                current_match = Match(i, j + 1, score, indent * num_indents)

                if raw_score >= 99.99:  # early exit, 99.99 for floating point error
                    logger.info(f"Exact match found! Returning: {current_match}")
                    return current_match

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


def split_ellipses(query: str) -> list[str]:
    queries = []
    current_query = ""
    for line in query.split("\n"):
        if line.strip() == "...":
            queries.append(current_query.strip("\n"))
            current_query = ""
        else:
            current_query += line + "\n"
    return queries


test_code = """\
capture_posthog_event(username, "started", properties=metadata)
...
capture_posthog_event(
    username,
    "failed",
    properties={"error": str(e), "reason": "Failed to get files", **metadata},
)
...
capture_posthog_event(
    username,
    "failed",
    properties={
        "error": "No files to change",
        "reason": "No files to change",
        **metadata,
    },
)
...
capture_posthog_event(
    username,
    "failed",
    properties={
        "error": str(e),
        "reason": "Failed to make changes",
        **metadata,
    },
)
...
capture_posthog_event(username, "success", properties={**metadata})
"""

if __name__ == "__main__":
    # for section in split_ellipses(test_code):
    #     print(section)
    code_file = r"""
    try:
        logger.info("Fetching files to modify/create...")
        if file_comment:
            file_change_requests = [
                FileChangeRequest(
                    filename=pr_file_path,
                    instructions=f"The user left a comment in this chunk of code:\n<review_code_chunk>{formatted_pr_chunk}\n</review_code_chunk>.\nResolve their comment.",
                    change_type="modify",
                )
            ]
        else:
            regenerate = comment.strip().lower().startswith("sweep: regenerate")
            reset = comment.strip().lower().startswith("sweep: reset")
            if regenerate or reset:
                logger.info(f"Running {'regenerate' if regenerate else 'reset'}...")

                file_paths = comment.strip().split(" ")[2:]

                def get_contents_with_fallback(repo: Repository, file_path: str):
                    try:
                        return repo.get_contents(file_path)
                    except SystemExit:
                        raise SystemExit
                    except Exception as e:
                        logger.error(e)
                        return None

                old_file_contents = [
                    get_contents_with_fallback(repo, file_path)
                    for file_path in file_paths
                ]

                logger.print(old_file_contents)
                for file_path, old_file_content in zip(file_paths, old_file_contents):
                    current_content = sweep_bot.get_contents(
                        file_path, branch=branch_name
                    )
                    if old_file_content:
                        logger.info("Resetting file...")
                        sweep_bot.repo.update_file(
                            file_path,
                            f"Reset {file_path}",
                            old_file_content.decoded_content,
                            sha=current_content.sha,
                            branch=branch_name,
                        )
                    else:
                        logger.info("Deleting file...")
                        sweep_bot.repo.delete_file(
                            file_path,
                            f"Reset {file_path}",
                            sha=current_content.sha,
                            branch=branch_name,
                        )
                if reset:
                    return {
                        "success": True,
                        "message": "Files have been reset to their original state.",
                    }
                return {
                    "success": True,
                    "message": "Files have been regenerated.",
                }
            else:
                non_python_count = sum(
                    not file_path.endswith(".py")
                    for file_path in human_message.get_file_paths()
                )
                python_count = len(human_message.get_file_paths()) - non_python_count
                is_python_issue = python_count > non_python_count
                file_change_requests, _ = sweep_bot.get_files_to_change(
                    is_python_issue, retries=1, pr_diffs=pr_diff_string
                )
                file_change_requests = sweep_bot.validate_file_change_requests(
                    file_change_requests, branch=branch_name
                )

            sweep_response = "I couldn't find any relevant files to change."
            if file_change_requests:
                table_message = tabulate(
                    [
                        [
                            f"`{file_change_request.filename}`",
                            file_change_request.instructions_display.replace(
                                "\n", "<br/>"
                            ).replace("```", "\\```"),
                        ]
                        for file_change_request in file_change_requests
                    ],
                    headers=["File Path", "Proposed Changes"],
                    tablefmt="pipe",
                )
                sweep_response = (
                    f"I decided to make the following changes:\n\n{table_message}"
                )
            quoted_comment = "> " + comment.replace("\n", "\n> ")
            response_for_user = (
                f"{quoted_comment}\n\nHi @{username},\n\n{sweep_response}"
            )
            if pr_number:
                edit_comment(response_for_user)
                # pr.create_issue_comment(response_for_user)
        logger.info("Making Code Changes...")

        blocked_dirs = get_blocked_dirs(sweep_bot.repo)

        sweep_bot.comment_pr_diff_str = pr_diff_string
        sweep_bot.comment_pr_files_modified = pr_files_modified
        changes_made = sum(
            [
                change_made
                for _, change_made, _, _ in sweep_bot.change_files_in_github_iterator(
                    file_change_requests, branch_name, blocked_dirs
                )
            ]
        )
        try:
            if comment_id:
                if changes_made:
                    # PR Review Comment Reply
                    edit_comment("Done.")
                else:
                    # PR Review Comment Reply
                    edit_comment(
                        'I wasn\'t able to make changes. This could be due to an unclear request or a bug in my code.\n As a reminder, comments on a file only modify that file. Comments on a PR(at the bottom of the "conversation" tab) can modify the entire PR. Please try again or contact us on [Discord](https://discord.com/invite/sweep)'
                    )
        except SystemExit:
            raise SystemExit
        except Exception as e:
            logger.error(f"Failed to reply to comment: {e}")

        if not isinstance(pr, MockPR):
            if pr.user.login == GITHUB_BOT_USERNAME and pr.title.startswith("[DRAFT] "):
                # Update the PR title to remove the "[DRAFT]" prefix
                pr.edit(title=pr.title.replace("[DRAFT] ", "", 1))

        logger.info("Done!")
    except NoFilesException:
        posthog.capture(
            username,
            "failed",
            properties={
                "error": "No files to change",
                "reason": "No files to change",
                **metadata,
            },
        )
        edit_comment(ERROR_FORMAT.format(title="Could not find files to change"))
        return {"success": True, "message": "No files to change."}
    except Exception as e:
        logger.error(traceback.format_exc())
        posthog.capture(
            username,
            "failed",
            properties={
                "error": str(e),
                "reason": "Failed to make changes",
                **metadata,
            },
        )
        edit_comment(ERROR_FORMAT.format(title="Failed to make changes"))
        raise e

    # Delete eyes
    if reaction is not None:
        item_to_react_to.delete_reaction(reaction.id)

    try:
        item_to_react_to = pr.get_issue_comment(comment_id)
        reaction = item_to_react_to.create_reaction("rocket")
    except SystemExit:
        raise SystemExit
    except Exception:
        try:
            item_to_react_to = pr.get_review_comment(comment_id)
            reaction = item_to_react_to.create_reaction("rocket")
        except SystemExit:
            raise SystemExit
        except Exception:
            pass

    try:
        if response_for_user is not None:
            edit_comment(f"## 🚀 Wrote Changes\n\n{response_for_user}")
    except SystemExit:
        raise SystemExit
    except Exception:
        pass

    posthog.capture(username, "success", properties={**metadata})
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

    search_query = r"""
    try:
        logger.info("Fetching files to modify/create...")
    ...
    posthog.capture(username, "success", properties={**metadata}) """

    # Find the best match
    best_span = find_best_match(search_query, code_file)
    # best_code_snippet = "\n".join(
    #     code_file.split("\n")[best_span.start : best_span.end]
    # )
    # print(f"Best code snippet:\n{best_code_snippet}")
    # print(f"Best match line numbers: {best_span.start}-{best_span.end}")
