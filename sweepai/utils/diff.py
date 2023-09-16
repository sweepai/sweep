import difflib
import re
from logn import logger

from sweepai.core.entities import SweepContext
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
    result_file = ""
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
    index = -1
    line_matches = 0
    num_hits = 0

    # # sliding window comparison from original to search
    # # Todo: 2 pointer approach (find start, then find end)
    # # Todo: use rapidfuzz to compute fuzzy similarity over code
    # for i in range(start_index or 0, len(original)):
    #     count = 0
    #     for j in range(len(search)):
    #         if i + j >= len(original):
    #             continue

    #         original_line = original[i + j]
    #         original_line = original_line.rsplit("#")[0].rsplit("//")[0]

    #         match = (
    #             search[j] == original_line
    #             if exact_match
    #             else search[j].strip() == original_line.strip()
    #         )
    #         if match:
    #             count += 1
    #     if count > line_matches:
    #         index = i
    #         print("line_matches: ", line_matches)
    #         line_matches = count
    #         num_hits = 1
    #     elif count == line_matches:
    #         num_hits += 1

    # if num_hits != 1 or line_matches / len(search) < 0.8:
    # if False:
    # if True:
    best_match = find_best_match("\n".join(search), "\n".join(original))
    # else:
    #     import pdb; pdb.set_trace()
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
    if len(search[0]) - len(search[0].lstrip()) == 0:
        num_whitespace = len(snippet[0]) - len(snippet[0].lstrip())
        if num_whitespace > 0:
            spaces = (
                snippet[0][0] * num_whitespace
            )  # Use first character (tab or space)
        else:
            spaces = ""
        strip = False
    else:  # Do diff between snippet and search
        # Todo(lukejagg): This might need to be more robust.

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


# Todo: issues with replace being shorter/longer than search
# def radix_replace(original, search, replace) -> tuple[list[str], bool]:
#     # remove all whitespaces from all texts for comparison
#     check_if_span_is_subspan = lambda little_span, big_span: "".join(
#         [s.strip() for s in little_span]
#     ) in "".join([s.strip() for s in big_span])
#     # always anchor on the original line
#     first_line = search[0]
#     if first_line not in original:
#         return None
#     first_line_idx = original.index(first_line)
#     # check if the rest of the lines are in the original
#     for second_pointer in range(
#         1, len(search)
#     ):  # when this loop terminates, it becomes a two pointer approach
#         match_span = search[second_pointer:]
#         if check_if_span_is_subspan(match_span, original[first_line_idx:]):
#             # check with whitespace
#             if match_span[0] not in original:
#                 continue
#             # TODO: perhaps we shouldn't match cases like ")" ? but leaving for now
#             # get the match
#             end_idx = original.index(match_span[0])
#             original = (
#                 original[:first_line_idx]
#                 + replace
#                 + original[end_idx + len(match_span) :]
#             )
#             return original
#     return None

# def detect_indent(code_str):
#     indents = re.findall(r'^(\s+)\S', code_str, re.MULTILINE)
#     counts = {'  ': 0, '    ': 0, '\t': 0}

#     for indent in indents:
#         if indent.startswith('    '):
#             counts['    '] += 1
#         elif indent.startswith('  '):
#             counts['  '] += 1
#         elif indent.startswith('\t'):
#             counts['\t'] += 1

#     return max(counts, key=counts.get) if counts else '    '

# def indent_replace(
#     old_lines: list[str],
#     search: list[str],
#     replace: list[str],
#     indent="    "
# ):
#     search_indent = (len(search[0]) - len(search[0].lstrip())) // len(indent)
#     replace_indent = (len(replace[0]) - len(replace[0].lstrip())) // len(indent)
#     indent_diff = replace_indent - search_indent
#     if indent_diff > 0:
#         # add indent
#         replace = [indent * indent_diff + line for line in replace]
#     elif indent_diff < 0:
#         # remove indent
#         replace = [line[-indent_diff:] for line in replace]
#     return replace

# def radix_replace(original, search, replace) -> tuple[list[str], bool]:
#     # based on start and end, find the lines that are the same
#     # then, replace the lines in between

#     best_match = match_string(original, search)
#     old_lines = original[best_match.start : best_match.end]
#     indent = detect_indent("\n".join(original))
#     original = original[: best_match.start] + indent_replace(old_lines, search, replace, indent) + original[best_match.end + 1 :]
# MAX_RADIX = 20
# Two-pointer approach for string matching
# for i in range(len(original)):
#     for j in range(
#         i + len(search) - 1, len(original) + len(search) + MAX_RADIX + 1
#     ):
#         # If second pointer is out of bounds, continue
#         if j >= len(original):
#             continue

#         # Match ends
#         match_start = original[i].strip() == search[0].strip()
#         match_end = original[j].strip() == search[-1].strip()
#         if not match_start or not match_end:
#             continue

#         # Counts the number of search matches with original code in this snippet (from i to j)
#         matches = []
#         current_index = i
#         count = 0  # Number of matches
#         while current_index <= j and count < len(search):
#             if original[current_index].strip() == search[count].strip():
#                 matches.append(current_index)
#                 count += 1
#             current_index += 1

#         # If exact match, do not use this algorithm as this is for skipped lines (comments)
#         if j - i == len(search) - 1:
#             return None

#         # If all lines matched in this snippet, then replace
#         if count == len(search):
#             # Replace search lines with replace lines
#             for i, original_index in enumerate(matches):
#                 if i < len(replace):
#                     original[original_index] = replace[i]

#             if len(replace) > len(search):
#                 # Add lines after the end of search if replace is longer
#                 original = (
#                     original[: original_index + 1]
#                     + replace[len(search) :]
#                     + original[original_index + 1 :]
#                 )
#             else:
#                 # Remove lines after end of search if replace is shorter
#                 original = (
#                     original[:original_index]
#                     + original[original_index + len(search) - len(replace) :]
#                 )
# return original


def sliding_window_replacement(
    original, search, replace, search_context_before=None, **kwargs
):
    if search == replace:
        return original
    status, replace_index = None, None
    # First, do check for "..." (example: define method, then put ... to ignore initial lines)
    canDoDotCheck = not any(
        "..." in line.strip() for line in original
    )  # If ... not in original file
    if canDoDotCheck:
        # Check first 3 lines for '...'
        first_line_idx = -1
        for i in range(len(search)):
            if search[i].strip() == "...":
                first_line_idx = i
                break

        # Do this for replace too
        first_line_idx_replace = -1
        for i in range(len(replace)):
            if replace[i].strip() == "...":
                first_line_idx_replace = i
                break
        if first_line_idx == 0 and first_line_idx_replace == 0:
            search = search[1:]
            replace = replace[1:]
        elif (
            first_line_idx == len(search) - 1
            and first_line_idx_replace == len(replace) - 1
        ):
            search = search[:first_line_idx]
            replace = replace[:first_line_idx_replace]
        elif first_line_idx != -1 and first_line_idx_replace != -1:
            # SPLIT INTO TWO PARTS
            # TODO(lukejagg): pass in the first and last lines as context for matching (so ambiguous ... can be matched)
            search_context_before = search[:first_line_idx]
            original, best_match, status = sliding_window_replacement(
                original,
                search[first_line_idx + 1 :],
                replace[first_line_idx_replace + 1 :],
                search_context_before,
                **kwargs,
            )
            search = search[:first_line_idx]
            replace = replace[:first_line_idx_replace]

    # exact_match = kwargs.get("exact_match", False)
    # ignore_comments = kwargs.get("ignore_comments", False)
    # index, max_similarity, current_hits = match_string(
    #     original, search, exact_match=exact_match, ignore_comments=ignore_comments
    # )
    best_match = match_string(original, search)
    logger.print(best_match)
    max_similarity = best_match.score
    # index = best_match.start

    # No changes could be found. Return original code.
    if max_similarity == 0:
        # # If there is only one line, then try to replace it
        # if (
        #     len(search) == 1
        #     and len(replace) == 1
        #     and sum(o.count(search[0]) for o in original) == 1
        # ):
        #     # Get index in original that has the search line
        #     index = [i for i, o in enumerate(original) if search[0] in o][0]
        #     # Replace that line with the replace line
        #     original[index] = original[index].replace(search[0], replace[0])
        #     return original, index, None

        # if not ignore_comments:  # In case Sweep decided not to include comments
        #     # Todo(lukejagg): Implement ignoring comments
        #     return sliding_window_replacement(
        #         original,
        #         search,
        #         replace,
        #         ignore_comments=True,
        #         **{k: v for k, v in kwargs.items() if k != "ignore_comments"},
        #     )
        # print("WARNING: No identical lines")
        # return original, None, IDENTICAL_LINES
        raise Exception("No identical lines")

    if max_similarity < 50:
        logger.print(f"Low similarity: {max_similarity}")

    # if current_hits > 1:
    #     success = False
    #     if search_context_before:
    #         old_index, _, current_hits = match_string(
    #             original,
    #             search_context_before,
    #             exact_match=exact_match,
    #         )
    #         _, old_spaces, _ = get_snippet_with_padding(
    #             original, old_index, search_context_before
    #         )

    #         if current_hits == 1:
    #             index, max_similarity, current_hits = match_string(
    #                 original,
    #                 [old_spaces + s for s in search],
    #                 start_index=old_index + 1,
    #                 exact_match=exact_match,
    #             )
    #             current_hits = 1  # Ignore multiple hits, use first complete comparison
    #             success = True

    #     if not success:
    #         if (
    #             len(replace) == 1 and not replace[0] and not search_context_before
    #         ):  # Backup 1: independent line matches
    #             exact_matches = [line for line in original if line in search]
    #             # If there are no duplicates and all lines have a match
    #             if len(set(exact_matches)) == len(search):
    #                 # Remove all of those corresponding lines in the content
    #                 original = [line for line in original if line not in search]
    #                 return original, None, None

    #         if not exact_match:  # Backup 2: exact line matches
    #             return sliding_window_replacement(
    #                 original,
    #                 search,
    #                 replace,
    #                 exact_match=True,
    #                 **{k: v for k, v in kwargs.items() if k != "exact_match"},
    #             )

    #         print("WARNING: Multiple hits")
    #         return original, None, MULTIPLE_HITS

    # Todo(lukejagg): Remove unreachable code
    # if index == -1:
    #     # First, try matching beginning of search
    #     return original, None, NOT_FOUND

    # Todo(lukejagg): this doesn't seem to work, add later
    # if int(max_similarity) != len(search):
    #     return original, None, INCOMPLETE_MATCH

    # if max_similarity != len(search):
    snippet, spaces, strip = get_snippet_with_padding(original, best_match, search)
    if len(snippet) == 1:
        # Replace the line
        modified = [snippet[0].replace(search[0], replace[0])]
    elif strip:
        # Todo: What if whitespace in search is incorrect
        first_line_spaces = min([len(s) - len(s.lstrip()) for s in search])
        modified = [
            spaces
            + (lstrip_max(line, [" ", "\t"], first_line_spaces) if strip else line)
            for line in replace
        ]
    else:
        modified = [spaces + line for line in replace]
    # replaced original with modified
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
