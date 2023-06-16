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

def format_contents(file_contents):
    """
    Add arbitrary postprocessing here 
    """
    lines = file_contents.split('\n')
    for i in range(len(lines) - 1, -1, -1):
        # If a line is a triple backtick or empty (whitespace),
        # replace it with an empty string
        if lines[i].strip() == '```' or not lines[i].strip():
            lines = lines[:i]
        else:
            # Stop when we hit a non-whitespace and non-backtick line
            break
    return '\n'.join(lines)