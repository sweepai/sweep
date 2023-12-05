helper_methods_contents = """# Helper functions for code modification. Run exec() on this file to load the functions into memory.
import ast
import difflib

file_path = '{target_file_id}'
with open(file_path, 'r') as file:
    file_content = file.read()
original_lines = file_content.splitlines()
current_content = file_content

def print_original_lines(i: int, j: int):
    \"\"\"
    Displays the original lines between line numbers i and j.
    \"\"\"
    start = max(0, i - 10)
    end = min(len(original_lines), j + 10)

    for index in range(start, end):
        if index == i:
            print("\\n--- Start of snippet ---")
        elif index == j:
            print("--- End of snippet ---\\n")

        print(f"{{index}}: {{original_lines[index]}}")
    print("\\n")

def print_original_lines_with_keywords(keywords: list[str]):
    \"\"\"
    Displays the original lines when any of the keywords are found.
    Use single words.
    \"\"\"
    context = 10

    matches = [i for i, line in enumerate(original_lines) if any(keyword in line.lower() for keyword in keywords)]
    expanded_matches = set()

    for match in matches:
        start = max(0, match - context)
        end = min(len(original_lines), match + context + 1)
        for i in range(start, end):
            expanded_matches.add(i)

    for i in sorted(expanded_matches):
        print(f"{{i}}: {{original_lines[i]}}")

def check_valid_python(code):
    \"\"\"
    Check if the code is valid python using ast.parse. Use this to check if python code is valid after making edits.
    \"\"\"
    try:
        # Check for valid python
        ast.parse(code)
        print("Python code is valid.")
    except SyntaxError as e:
        print("Python SyntaxError:", e)

def print_diff(new_content, old_content=file_content, final_diff=False):
    if new_content == old_content:
        print("No changes were made. Please try again to produce a valid diff.")
    unified_diff = difflib.unified_diff(
        old_content.split("\\n"), new_content.split("\\n")
    )
    unified_diff_str = '\\n'.join([diff_line.strip("\\n") for diff_line in unified_diff])
    if final_diff:
        print(f"<final_diff>\\n{{unified_diff_str}}\\n</final_diff>")
    else:
        print(f"<diff>\\n{{unified_diff_str}}\\n</diff>")

def set_indentation(code, num_indents=4):
    \"\"\"
    Set the indentation of the code to num_indents.
    Use this to programmatically indent code that is not indented properly.
    \"\"\"
    lines = [line for line in code.split('\\n') if line.strip()]
    min_indent = min(len(line) - len(line.lstrip()) for line in lines)
    return '\\n'.join(' ' * num_indents + line[min_indent:] for line in lines)"""


# exec(helper_methods_contents.format(target_file_id='sweepai/utils/ticket_utils.py'))
# import pdb; pdb.set_trace()
# unified_diff = difflib.unified_diff(file_content.split("\n"), new_content.split("\n"))
# new_content = file_content + "a"; print_diff(new_content, file_content)
# to test just uncomment all this code
