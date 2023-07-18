import difflib
import re

def diff_contains_dups_or_removals(diff, new_code):
    # The regex pattern for lines removed or added in the actual code
    removed_line_pattern = r"^-.*"
    added_line_pattern = r"^\+.*"

    lines_removed = False
    duplicate_lines_added = False

    # Split the diff and new_code into separate lines
    diff_lines = diff.split('\n')[3:]  # Start from the third line
    new_code_lines = [line.strip() for line in new_code.split('\n')]

    # Check if there are removed lines
    for line in diff_lines:
        if re.match(removed_line_pattern, line):
            lines_removed = True

    # Check if there are duplicate lines added
    added_lines = [line[1:].strip() for line in diff_lines if re.match(added_line_pattern, line)]
    for line in added_lines:
        if new_code_lines.count(line) > 1:
            duplicate_lines_added = True
            break

    return lines_removed or duplicate_lines_added

def generate_diff(old_code, new_code):
    old_code = old_code.strip()
    new_code = new_code.strip()
    
    diff = difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True)
    )

    diff_text = ''.join(diff)
    
    return diff_text

def revert_whitespace_changes(original_file_str, modified_file_str):
    original_lines = original_file_str.splitlines()
    modified_lines = modified_file_str.splitlines()

    diff = difflib.SequenceMatcher(None, original_lines, modified_lines)

    final_lines = []
    for opcode in diff.get_opcodes():
        if opcode[0] == "equal" or opcode[0] == "replace":
            # If the lines are equal or replace (means the change is not whitespace only)
            # use original lines.
            final_lines.extend(original_lines[opcode[1]:opcode[2]])
        elif opcode[0] == "insert":
            # If the lines are inserted in the modified file, check if it's just whitespace changes
            # If it's just whitespace changes, ignore them.
            for line in modified_lines[opcode[3]:opcode[4]]:
                if line.strip() != "":
                    final_lines.append(line)

    return '\n'.join(final_lines)


def format_contents(file_contents, is_markdown=False):
    """
    Add arbitrary postprocessing here, this affects files and diffs
    """
    lines = file_contents.split('\n')

    if is_markdown:
        return '\n'.join(lines)

    # Handle small files
    if len(lines) <= 5:
        start_idx = 0
        end_idx = len(lines)
        for idx, line in enumerate(lines):
            if start_idx == 0 and line.strip().startswith('```'):
                start_idx = idx + 1
            if start_idx != 0 and line.strip().endswith('```'):
                end_idx = idx
        lines = lines[start_idx:end_idx]
        return '\n'.join(lines)

    first_three_lines = lines[:3]
    last_three_lines = lines[-3:]
    first_line_idx = 0
    last_line_idx = 3
    for idx, line in enumerate(first_three_lines):
        line = line.strip()
        if line.startswith('```'):
            first_line_idx = max(first_line_idx, idx + 1)
        if 'user_code>' in line:
            first_line_idx = max(first_line_idx, idx + 1)
    for idx, line in enumerate(last_three_lines): # Check in reverse
        line = line.strip()
        if line.endswith('```'):
            last_line_idx = min(idx, last_line_idx)
        if 'user_code>' in line:
            last_line_idx = min(idx, last_line_idx)
    first_three_lines = first_three_lines[first_line_idx:]
    last_three_lines = last_three_lines[:last_line_idx]

    lines = first_three_lines + lines[3:-3] + last_three_lines
    return '\n'.join(lines)


def generate_new_file(modify_file_response: str, old_file_content: str, chunk_offset: int=0) -> str:
    import re

    result_file = ""
    old_file_lines = old_file_content.splitlines()

    # Extract content between <new_file> tags
    match = re.search(r".*?<new_file>\n?(.*)\n<\/new_file>", modify_file_response, re.DOTALL)
    if match is None:
        return None
    new_file = match.group(1)
    if new_file is None:
        return None

    # v5
    result = []
    lines = new_file.split('\n')
    for line_number, line in enumerate(lines):
        # Todo: make it support 1 number only
        matches = re.finditer(r"<copy_lines\s(\d+-\d+)/?>", line)
        copied_lines = False
        for match in matches:
            copied_lines = True
            start, end = match.group(1).split('-')
            start, end = int(start) - 1, int(end) - 1
            if chunk_offset != 0: # Correct for the line numbers being much higher
                start -= chunk_offset
                end -= chunk_offset
            start = max(0, start)
            end = min(len(old_file_lines) - 1, end)

            replacements = old_file_lines[start:end + 1]
            replacements_str = '\n'.join(replacements)
            line = line.replace(match.group(0), replacements_str)

        # check if line was incorrectly duplicated
        append = True
        if not copied_lines:  # if bot generated, and line before is not bot generated
            if len(result) > 0:
                # Get last line in results
                last_group = result[-1]
                # last_line = last_group
                if '\n' in last_group:
                    last_line = last_group[last_group.rindex('\n') + 1:]  # if its multiple lines
                    # if last line is same is current line
                    if last_line == line:
                        append = False

        if append:
            result.append(line)
    result = '\n'.join(result)

    # Todo: v4 is inefficient; deprecated
    """
    first_section_idx = new_file.index("<copied>")
    if first_section_idx > 0:
        result_file += new_file[:first_section_idx]
        new_file = new_file[first_section_idx:] # remove the first section from new_file
    last_section_idx = new_file.rindex("</copied>")
    last_section = ""
    if last_section_idx < len(new_file) - 1:
        last_section = new_file[last_section_idx + len("</copied>"):]
        new_file = new_file[:last_section_idx + len("</copied>")] # remove the last section from new_file
    
    # Parse copied sections, first copying the content and then adding whatever is after the copied section
    for copied_section in copied_sections:
        if "-" in copied_section:
            start_line, end_line = copied_section.split("-")
        else: # <copied>num</copied>
            start_line = copied_sections
            end_line = start_line

        start_line = int(start_line) - 1 if int(start_line) - 1 > 0 else 0
        end_line = int(end_line) - 1
        # Check for duplicate lines
        k = 30
        result_file = join_contents_k(result_file, "\n".join(old_file_lines[start_line:end_line]), k)
        # TODO: Use replace first instead of .replace, since duplicated <copied> sections might cause faulty copy
        new_file = new_file.replace(f"<copied>{copied_section}</copied>\n", "")
        next_section_idx = new_file.index("<copied>") if "<copied>" in new_file else len(new_file)
        # Check for duplicate lines
        result_file = join_contents_k(result_file, new_file[:next_section_idx], k)
        new_file = new_file[next_section_idx:] # remove the first section from new_file
    
    return result_file + last_section
    """

    return result


def join_contents_k(first, second, k):
    """
    Join contents together removing k duplicate lines
    """
    first_lines = first.splitlines()
    second_lines = second.splitlines()
    for i in range(k, 0, -1):
        if len(first_lines) < k or len(second_lines) < k:
            continue
        if first_lines[-i:] == second_lines[:i]:
            return "\n".join(first_lines) + "\n" + "\n".join(second_lines[i:])
    return "\n".join(first_lines) + "\n" + "\n".join(second_lines)


def is_markdown(filename):
    return filename.endswith(".md") or filename.endswith(".rst") or filename.endswith(".txt")
