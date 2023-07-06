from sweepai.utils.diff import generate_diff
import difflib

old = """import os

"""
new = """import abc

"""

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

print(f"File: {revert_whitespace_changes(old, new)}")