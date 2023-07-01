import difflib
import re


def generate_diff(old_code, new_code):
    diff = difflib.unified_diff(
        old_code.splitlines(keepends=True), new_code.splitlines(keepends=True)
    )
    return "".join(diff)


def format_contents(file_contents, is_markdown=False):
    """
    Add arbitrary postprocessing here, this affects files and diffs
    """
    lines = file_contents.split("\n")
    code_lines = []
    in_code_block = True

    if is_markdown:
        return "\n".join(lines) + "\n"
    for line in lines:
        stripped_line = line.strip()

        # Check if line starts a code block
        if stripped_line.startswith("```") and not in_code_block:
            in_code_block = True
            continue

        # Check if line ends a code block
        if stripped_line.endswith("```") and in_code_block:
            in_code_block = False
            continue

        # Append line if it's inside a code block or if it's not an empty line
        if not in_code_block:
            continue
        code_lines.append(line)

    return "\n".join(code_lines) + "\n"


def generate_new_file(modify_file_response: str, old_file_content: str) -> str:
    import re

    result_file = ""
    old_file_lines = old_file_content.splitlines()

    # Extract content between <new_file> tags
    new_file = (
        re.search(r"<new_file>(.*?)<\/new_file>", modify_file_response, re.DOTALL)
        .group(1)
        .strip()
    )
    if "<copied>" not in new_file:
        return new_file

    # Find all <copied> tags and their content
    copied_sections = re.findall(r"<copied>(.*?)<\/copied>", new_file, re.DOTALL)

    first_section_idx = new_file.index("<copied>")
    if first_section_idx > 0:
        result_file += new_file[:first_section_idx]
        new_file = new_file[
            first_section_idx:
        ]  # remove the first section from new_file
    last_section_idx = new_file.rindex("</copied>")
    last_section = ""
    if last_section_idx < len(new_file) - 1:
        last_section = new_file[last_section_idx + len("</copied>") :]
        new_file = new_file[
            : last_section_idx + len("</copied>")
        ]  # remove the last section from new_file

    # Parse copied sections, first copying the content and then adding whatever is after the copied section
    for copied_section in copied_sections:
        start_line, end_line = copied_section.split("-")
        start_line = int(start_line) - 1 if int(start_line) - 1 > 0 else 0
        end_line = int(end_line)
        # Check for duplicate lines
        k = 30
        result_file = join_contents_k(
            result_file, "\n".join(old_file_lines[start_line:end_line]), k
        )
        new_file = new_file.replace(f"<copied>{copied_section}</copied>\n", "")
        next_section_idx = (
            new_file.index("<copied>") if "<copied>" in new_file else len(new_file)
        )
        # Check for duplicate lines
        result_file = join_contents_k(result_file, new_file[:next_section_idx], k)
        new_file = new_file[next_section_idx:]  # remove the first section from new_file
    return result_file + last_section


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
    return (
        filename.endswith(".md")
        or filename.endswith(".rst")
        or filename.endswith(".txt")
    )
