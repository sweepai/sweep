import difflib
import re


def fuse_files(old_file_content: str, new_file_content: str):
    """
    Replaces the new code with the old code when "Rest of code..." shows up.
    """
    old_file_content = old_file_content.strip("\n")
    new_file_content = new_file_content.strip("\n")

    def match(line):
        lowercase = line.lower().strip()
        semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
        is_comment = lowercase.startswith("#") or lowercase.startswith("//")
        return semantic_match and is_comment

    old_lines = old_file_content.splitlines()
    new_lines = new_file_content.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    result_lines = []
    inserts = []
    deleted_lines = []
    sequence_match_op_codes = matcher.get_opcodes() # These are tag, old_start_idx, old_end_idx, new_start_idx, new_end_idx
    sequence_match_op_codes.sort(key=lambda x: x[3]) # Sort it by the new_start_idx
    sequence_match_op_codes = [(tag, i1, i2, j1, j2, old_lines[i1:i2], new_lines[j1:j2]) for tag, i1, i2, j1, j2 in sequence_match_op_codes]
    for tag, _, _, _, j2, old_chunk, new_chunk in sequence_match_op_codes:
        if tag == 'equal':
            result_lines.append('\n'.join(old_chunk))
        elif tag == 'replace':
            for line in new_chunk:
                if match(line):
                    result_lines.append('\n'.join(old_chunk))
                else:
                    result_lines.append(line)
        elif tag == 'delete':
            deleted_lines.extend(old_chunk)  # Store deleted lines for later use
        elif tag == 'insert':
            for line in new_chunk:
                if match(line):
                    inserts.append((j2, deleted_lines))  # Store the insert operation and associated deleted lines for later
                else:
                    result_lines.append(line)

    # Process insert operations that were stored for later
    for j2, lines in inserts:
        result_lines.insert(j2, '\n'.join(lines))
    result_lines = [line.rstrip() for line in result_lines]
    return '\n'.join(result_lines).strip('\n') + '\n'

def format_contents(file_contents, is_markdown=False):
    """
    Add arbitrary postprocessing here, this affects files and diffs
    """
    lines = file_contents.split('\n')
    code_lines = []
    in_code_block = False

    if is_markdown:
        if lines[0].startswith('```'):
            lines = lines[1:]
        if lines[-1].startswith('```'):
            lines = lines[:-1]
        return '\n'.join(lines) + '\n'
    for line in lines:
        stripped_line = line.strip()

        # Check if line starts a code block
        if stripped_line.startswith('```') and not in_code_block:
            in_code_block = True
            continue

        # Check if line ends a code block
        if stripped_line.endswith('```') and in_code_block:
            in_code_block = False
            continue

        # Append line if it's inside a code block or if it's not an empty line
        if in_code_block or stripped_line:
            code_lines.append(line)

    return '\n'.join(code_lines) + '\n'


def generate_new_file(modify_file_response: str, old_file_content: str) -> str:
    import re

    result_file = ""
    old_file_lines = old_file_content.splitlines()

    # Extract content between <new_file> tags
    new_file = re.search(r"<new_file>(.*?)<\/new_file>", modify_file_response, re.DOTALL).group(1).strip()

    # Find all <copied> tags and their content
    copied_sections = re.findall(r"<copied>(.*?)<\/copied>", new_file, re.DOTALL)
    
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
        start_line, end_line = copied_section.split("-")
        start_line = int(start_line) - 1 if int(start_line) - 1 > 0 else 0
        end_line = int(end_line)
        # Check for duplicate lines
        k = 30
        result_file = join_contents_k(result_file, "\n".join(old_file_lines[start_line:end_line]), k)
        new_file = new_file.replace(f"<copied>{copied_section}</copied>\n", "")
        next_section_idx = new_file.index("<copied>") if "<copied>" in new_file else len(new_file)
        # Check for duplicate lines
        result_file = join_contents_k(result_file, new_file[:next_section_idx], k)
        new_file = new_file[next_section_idx:] # remove the first section from new_file
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
    return filename.endswith(".md") or filename.endswith(".rst") or filename.endswith(".txt")