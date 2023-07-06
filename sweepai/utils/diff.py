import difflib
import re

def generate_diff(old_code, new_code):
    diff = difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True)
    )
    return ''.join(diff)

def format_contents(file_contents, is_markdown=False):
    '''
    Add arbitrary postprocessing here, this affects files and diffs
    '''
    lines = file_contents.split('\n')
    # Check if the file is a Python file before removing whitespace lines
    if file_contents.endswith('.py'):
        lines = [line for line in lines if line.strip() != '']
    else:
        lines = file_contents.split('\n')

    if is_markdown:
        return '\n'.join(lines) + '\n'
    
    # Handle small files
    if len(lines) <= 5:
        final_lines = []
        start_idx = 0
        end_idx = len(lines)
        for idx, line in enumerate(lines):
            if start_idx == 0 and line.strip().startswith('```'):
                start_idx = idx
            if start_idx != 0 and line.strip().endswith('```'):
                end_idx = idx
        lines = lines[start_idx + 1:end_idx]
        return '\n'.join(lines) + '\n'

    first_three_lines = lines[:3]
    last_three_lines = lines[-3:]
    first_line_idx = 0
    last_line_idx = 3
    for idx, line in enumerate(first_three_lines):
        line = line.strip()
        if line.startswith('```'):
            first_line_idx = idx + 1
    for idx, line in enumerate(last_three_lines):
        line = line.strip()
        if line.endswith('```'):
            last_line_idx = idx
    first_three_lines = first_three_lines[first_line_idx:]

    lines = first_three_lines + lines[3:-3] + last_three_lines
    return '\n'.join(lines) + '\n'

def generate_new_file(modify_file_response: str, old_file_content: str) -> str:
    import re

    result_file = ""
    old_file_lines = old_file_content.splitlines()

    # Extract content between <new_file> tags
    new_file = re.search(r"<new_file>(.*?)<\/new_file>", modify_file_response, re.DOTALL).group(1).strip()
    if "<copied>" not in new_file:
        return new_file

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
        if "-" in copied_section:
            start_line, end_line = copied_section.split("-")
        else: # <copied>num</copied>
            start_line = copied_sections
            end_line = start_line

        start_line = int(start_line) - 1 if int(start_line) - 1 > 0 else 0
        end_line = int(end_line)
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

