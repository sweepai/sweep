# from sweepai.utils.diff import generate_diff
# import difflib

# old = """import os
# def main():
#      print("hello world")
# """
# new = """import abc
# def main():
#      print("hello world")

# """

# def revert_whitespace_changes(original_file_str, modified_file_str):
#     original_lines = original_file_str.splitlines()
#     modified_lines = modified_file_str.splitlines()

#     diff = difflib.SequenceMatcher(None, original_lines, modified_lines)

#     final_lines = []
#     for opcode in diff.get_opcodes():
#         print(opcode[0], original_lines[opcode[1]:opcode[2]], modified_lines[opcode[3]:opcode[4]])
#         if opcode[0] == "equal" or opcode[0] == "replace":
#             # If the lines are equal or replace (means the change is not whitespace only)
#             # use original lines.
#             replacement = modified_lines[opcode[3]:opcode[4]]
#             for line in replacement:
#                 if line.strip():  # Ignore lines that contain only whitespace
#                     final_lines.extend(modified_lines[opcode[3]:opcode[4]])
#                     break
#         elif opcode[0] == "insert":
#             # If the lines are inserted in the modified file, check if it's just whitespace changes
#             # If it's just whitespace changes, ignore them.
#             for line in modified_lines[opcode[3]:opcode[4]]:
#                 if line.strip():  # Ignore lines that contain only whitespace
#                     final_lines.extend(modified_lines[opcode[3]:opcode[4]])
#                     break
#         elif opcode[0] == "delete":
#             # If the lines are deleted in the original file, check if it's just whitespace changes
#             # If it's just whitespace changes, ignore them.
#             for line in original_lines[opcode[1]:opcode[2]]:
#                 if line.strip():  # Ignore lines that contain only whitespace
#                     final_lines.extend(original_lines[opcode[1]:opcode[2]])
#                     break

#     return '\n'.join(final_lines)

# print(f"START:\n{revert_whitespace_changes(old, new)}\nEND")


old = """import os
def main():
     print("hello world")

def main():
     print("hello world")
"""
new = """import abc

def main():
     print("hello world")
def main():
     print("hello world")

"""

expected = """import abc

def main():
     print("hello world")

def main():
     print("hello world")
"""
