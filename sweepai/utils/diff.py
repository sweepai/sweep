import difflib
import re

from sweepai.core.entities import SweepContext
from sweepai.logn import logger
from sweepai.utils.chat_logger import discord_log_error
from sweepai.utils.search_and_replace import Match, find_best_match


def diff_contains_dups_or_removals(diff, new_code):
    # The regex pattern for lines removed or added in the actual code
    removed_line_pattern = r"^-.*"
    added_line_pattern = r"^\+.*"

    lines_removed = False
    duplicate_lines_added = False

    # Split the diff and new_code into separate lines
    diff_lines = diff.split("\n")[3:]  # Start from the third line
    new_code_lines = [line.strip() for line in new_code.split("\n")]

    # Check if there are removed lines
    for line in diff_lines:
        if re.match(removed_line_pattern, line):
            lines_removed = True

    # Check if there are duplicate lines added
    added_lines = [
        line[1:].strip() for line in diff_lines if re.match(added_line_pattern, line)
    ]
    for line in added_lines:
        if new_code_lines.count(line) > 1:
            duplicate_lines_added = True
            break

    return lines_removed or duplicate_lines_added


def generate_diff(old_code, new_code):
    if old_code == new_code:
        return ""
    old_code = old_code.strip()
    new_code = new_code.strip()

    diff = difflib.unified_diff(
        old_code.splitlines(keepends=True), new_code.splitlines(keepends=True)
    )

    diff_text = "".join(diff)

    return diff_text


def revert_whitespace_changes(original_file_str, modified_file_str):
    original_lines = original_file_str.split("\n")
    modified_lines = modified_file_str.split("\n")

    diff = difflib.SequenceMatcher(None, original_lines, modified_lines)

    final_lines = []
    for opcode in diff.get_opcodes():
        if opcode[0] == "equal" or opcode[0] == "replace":
            # If the lines are equal or replace (means the change is not whitespace only)
            # use original lines.
            final_lines.extend(original_lines[opcode[1] : opcode[2]])
        elif opcode[0] == "insert":
            # If the lines are inserted in the modified file, check if it's just whitespace changes
            # If it's just whitespace changes, ignore them.
            for line in modified_lines[opcode[3] : opcode[4]]:
                if line.strip() != "":
                    final_lines.append(line)

    return "\n".join(final_lines)


def format_contents(file_contents, is_markdown=False):
    """
    Add arbitrary postprocessing here, this affects files and diffs
    """
    lines = file_contents.split("\n")

    # Handle small files
    if len(lines) <= 5:
        start_idx = 0
        end_idx = len(lines)
        for idx, line in enumerate(lines):
            if start_idx == 0 and line.strip().startswith("```"):
                start_idx = idx + 1
            if start_idx != 0 and line.strip().endswith("```"):
                end_idx = idx
        lines = lines[start_idx:end_idx]
        return "\n".join(lines)

    first_three_lines = lines[:3]
    last_three_lines = lines[-3:]
    first_line_idx = 0
    last_line_idx = 3
    for idx, line in enumerate(first_three_lines):
        line = line.strip()
        if line.startswith("```"):
            first_line_idx = max(first_line_idx, idx + 1)
        if "user_code>" in line:
            first_line_idx = max(first_line_idx, idx + 1)
    for idx, line in enumerate(last_three_lines):  # Check in reverse
        line = line.strip()
        if line.endswith("```"):
            last_line_idx = min(idx, last_line_idx)
        if "user_code>" in line:
            last_line_idx = min(idx, last_line_idx)
    first_three_lines = first_three_lines[first_line_idx:]
    last_three_lines = last_three_lines[:last_line_idx]

    lines = first_three_lines + lines[3:-3] + last_three_lines
    return "\n".join(lines)


def generate_new_file(
    modify_file_response: str, old_file_content: str, chunk_offset: int = 0
) -> str:
    old_file_lines = old_file_content.split("\n")

    # Extract content between <new_file> tags
    new_file = re.search(
        r".*?<new_file>\n?(.*)\n<\/new_file>", modify_file_response, re.DOTALL
    ).group(1)
    if "<copy_lines" not in new_file:
        return new_file

    # v5
    result = []
    lines = new_file.split("\n")
    for line_number, line in enumerate(lines):
        # Todo: make it support 1 number only
        matches = re.finditer(r"<copy_lines\s(\d+-\d+)/?>", line)
        copied_lines = False
        for match in matches:
            copied_lines = True
            start, end = match.group(1).split("-")
            start, end = int(start) - 1, int(end) - 1
            if chunk_offset != 0:  # Correct for the line numbers being much higher
                start -= chunk_offset
                end -= chunk_offset
            start = max(0, start)
            end = min(len(old_file_lines) - 1, end)

            replacements = old_file_lines[start : end + 1]
            replacements_str = "\n".join(replacements)
            line = line.replace(match.group(0), replacements_str)

        # check if line was incorrectly duplicated
        append = True
        if not copied_lines:  # if bot generated, and line before is not bot generated
            if len(result) > 0:
                # Get last line in results
                last_group = result[-1]
                # last_line = last_group
                if "\n" in last_group:
                    last_line = last_group[
                        last_group.rindex("\n") + 1 :
                    ]  # if its multiple lines
                    # if last line is same is current line
                    if last_line == line:
                        append = False

        if append:
            result.append(line)
    result = "\n".join(result)

    return result


NOT_FOUND = "NOT_FOUND"
IDENTICAL_LINES = "NO MATCHES FOUND"
MULTIPLE_HITS = "MULTIPLE_HITS"
INCOMPLETE_MATCH = "INCOMPLETE_MATCH"


def match_string(original, search, start_index=None, exact_match=False) -> Match:
    pass

    best_match = find_best_match("\n".join(search), "\n".join(original))
    # else:
    #     best_match = Match(index, index + line_matches, score=100)
    logger.print(best_match)
    return best_match


def lstrip_max(s, chars, max_count):
    count = 0
    for char in s:
        if char in chars and count < max_count:
            count += 1
        else:
            break
    return s[count:]


def get_snippet_with_padding(original, best_match, search):
    snippet = original[best_match.start : best_match.end]

    # Fix whitespace
    if search and len(search[0]) - len(search[0].lstrip()) == 0:
        num_whitespace = len(snippet[0]) - len(snippet[0].lstrip())
        if num_whitespace > 0:
            spaces = (
                snippet[0][0] * num_whitespace
            )  # Use first character (tab or space)
        else:
            spaces = ""
        strip = False
    else:  # Do diff between snippet and search
        # Check multiple lines for their whitespace
        min_whitespace = min([len(s) - len(s.lstrip()) for s in search])
        # Rewrite min as for loop
        min_whitespace = None
        character = " "
        for line in search:
            if (
                min_whitespace is None
                or len(line) - len(line.lstrip()) < min_whitespace
            ):
                min_whitespace = len(line) - len(line.lstrip())
                if min_whitespace > 0:
                    character = line[0]
        spaces = character * min_whitespace
        strip = True

    return snippet, spaces, strip


def sliding_window_replacement(
    original: list[str],
    search: list[str],
    replace: list[str],
    search_context_before=None,
    **kwargs,
):
    if search == replace:
        return original, None, None

    best_match = match_string(original, search)
    logger.print(best_match)
    max_similarity = best_match.score

    # No changes could be found. Return original code.
    if max_similarity == 0:
        raise Exception("No identical lines")

    if max_similarity < 50:
        logger.print(f"Low similarity: {max_similarity}")

    snippet, spaces, strip = get_snippet_with_padding(original, best_match, search)
    if len(snippet) == 1 and len(replace) == 1:
        # Replace the line
        modified = [snippet[0].replace(search[0], replace[0])]
    elif strip:
        first_line_spaces = min([len(s) - len(s.lstrip()) for s in search])
        modified = [
            spaces
            + (lstrip_max(line, [" ", "\t"], first_line_spaces) if strip else line)
            for line in replace
        ]
    else:
        modified = [spaces + line for line in replace]

    for i in range(min(len(modified) * 2, 40), 0, -1):
        modified_str = "\n".join(modified[:i])
        original_str = "\n".join(original[best_match.start - i : best_match.start])
        modified_pref = "\n".join(modified[-i:])
        original_pref = "\n".join(original[best_match.end : best_match.end + i])
        if modified_str.strip("\n") == original_str.strip("\n"):
            modified = modified[i:]
        if modified_pref == original_pref:
            modified = modified[:-i]
    original = original[: best_match.start] + modified + original[best_match.end :]
    return original, best_match, None


def get_all_diffs(modify_file_response: str) -> str:
    matches = re.findall(
        r"(<<<<.*?\n(.*?)\n====[^\n=]*\n(.*?)\n?>>>>)", modify_file_response, re.DOTALL
    )
    result = "\n\n".join([_match for _match, *_ in matches])
    return result


def get_matches(modify_file_response):
    matches = re.findall(
        r"<<<<.*?\n(.*?)\n====[^\n=]*\n(.*?)\n?>>>>", modify_file_response, re.DOTALL
    )
    return matches


def generate_new_file_from_patch(
    modify_file_response: str,
    old_file_content: str,
    chunk_offset: int = 0,
    sweep_context: SweepContext = None,
):
    old_file_lines = old_file_content.split("\n")

    # Extract content between <new_file> tags
    matches = get_matches(modify_file_response)
    errors = []

    if not old_file_content.strip():
        # If old file is empty, just return the first match
        logger.print(matches)
        search_and_replace, *_ = matches
        return search_and_replace[1]

    for search, replace in matches:
        # Remove trailing tags
        if search.lstrip().startswith("<old_file>") and replace.lstrip().startswith(
            "<old_file>"
        ):
            search = search.lstrip()[len("<old_file>") :]
            replace = replace.lstrip()[len("<old_file>") :]
        # Remove trailing tags
        if search.rstrip().endswith("</old_file>") and replace.rstrip().endswith(
            "</old_file>"
        ):
            search = search.rstrip()[: -len("</old_file>")]
            replace = replace.rstrip()[: -len("</old_file>")]
        if replace.lstrip().startswith("<new_file>"):
            replace = replace.lstrip()[len("<new_file>") :]
        elif replace.lstrip().startswith("<updated_file>"):
            replace = replace.lstrip()[len("<updated_file>") :]
        if replace.rstrip().endswith("</new_file>"):
            replace = replace.rstrip()[: -len("</new_file>")]
        elif replace.rstrip().endswith("</updated_file>"):
            replace = replace.rstrip()[: -len("</updated_file>")]
        if replace.endswith("===="):
            replace = replace[: -len("====")]
        old_file_lines, best_match, status = sliding_window_replacement(
            old_file_lines, search.split("\n"), replace.split("\n")
        )

        if status is not None:
            s = search.replace("`", "\\`")
            r = replace.replace("`", "\\`")
            errors.append(f"- {status}\n```\n{s}\n```\n\n```\n{r}\n```")

    if len(errors) > 0:
        log = "\n\n".join(errors)
        if sweep_context:
            discord_log_error(
                f"{sweep_context.issue_url}\nModify Parsing Errors {'gpt3.5' if sweep_context.use_faster_model else 'gpt4'}: \n"
                + log,
                priority=2 if sweep_context.use_faster_model else 0,
            )
        else:
            discord_log_error(
                f"Modify Parsing Errors gpt3.5: \n" + log,
                priority=2,
            )

    result = "\n".join(old_file_lines)
    return result, errors


def join_contents_k(first, second, k):
    """
    Join contents together removing k duplicate lines
    """
    first_lines = first.split("\n")
    second_lines = second.split("\n")
    for i in range(k, 0, -1):
        if len(first_lines) < k or len(second_lines) < k:
            continue
        if first_lines[-i:] == second_lines[:i]:
            return "\n".join(first_lines) + "\n" + "\n".join(second_lines[i:])
    return "\n".join(first_lines) + "\n" + "\n".join(second_lines)


def is_markdown(filename):
    return (
        filename.endswith(".md")
        or filename.endswith(".rst")
        or filename.endswith(".txt")
    )


if __name__ == "__main__":
    old_file = """
a
b
c
"""

    search = "b"
    replace = """a
b"""
    print(
        "\n".join(
            sliding_window_replacement(
                old_file.split("\n"), search.split("\n"), replace.split("\n")
            )[0]
        )
    )
    old_file = '''

"""
on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py.
It is also called in sweepai/handlers/on_ticket.py when Sweep is reviewing its own PRs.
"""

'''

    search = "on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py."
    replace = '''
"""
on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py.
It is also called in sweepai/handlers/on_ticket.py when Sweep is reviewing its own PRs.
"""'''
    res = "\n".join(
        sliding_window_replacement(
            old_file.split("\n"), search.split("\n"), replace.split("\n")
        )[0]
    )
    assert old_file == res

    search = "on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py."
    replace = '''
"""
Add another test line
on_comment is responsible for handling PR comments and PR review comments, called from sweepai/api.py.
Add another test line'''
    res = "\n".join(
        sliding_window_replacement(
            old_file.split("\n"), search.split("\n"), replace.split("\n")
        )[0]
    )
    print(res)
    assert "Add another test line" in res
