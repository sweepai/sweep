from collections import defaultdict
from sweepai.config.client import SweepConfig

# post process rip grep output to be more condensed
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
    processed_output = ""
    output_lines = output.split("\n")
    # empty lines are present at end of output
    output_lines = [line for line in output_lines if line]
    file_output_dict = defaultdict()
    for line in output_lines:
        filename, content = line.split(":", 1)
        filename = filename[len(root_directory) + 1:]
        if not sweep_config.is_file_excluded_aggressive(root_directory, filename):
            if filename not in file_output_dict: file_output_dict[filename] = ""
            file_output_dict[filename] += (content + "\n")
    
    # determine if we need to truncate the output
    total_output_length = sum([len(line) for content in file_output_dict.values() for line in content])
    if total_output_length > sweep_config.truncation_cutoff:
        for filename, content in file_output_dict.items():
            processed_output += f"File: {filename} had the following matching lines of code"
            if len(content) < 4:
                processed_output += " :\n"
                for line in content:
                    processed_output += f"{line}\n"
            else:
                processed_output += " (some lines have been truncated):\n"
                line1 = content[0]
                line2 = content[-1]
                if len(line1) > 200:
                    line1 = line1[:20] + " ..."
                if len(line2) > 200:
                    line2 = line2[:20] + " ..."
                processed_output += f"{line1}\n"
                processed_output += "...\n"
                processed_output += f"{line2}\n"
            processed_output += "\n"
    else:
        for filename, content in file_output_dict.items():
            processed_output += f"File: {filename} had the following matching lines of code:\n" + content + "\n"
    return processed_output, file_output_dict

# try and find code inside chunk given various levels of indentation, and right strip the lines of code
# if successful returns the num of spaces required to find the code match and if we need to rstrip the old code or not
def manual_code_check(chunk: str, code: str) -> tuple[int, bool]:
    code_lines = [line for line in code.split("\n")]
    # assume one indent is two spaces and check max 10 indents
    for indent in range(0, 40, 2):
        new_code_lines = [f"{' ' * indent}{line}" for line in code_lines]
        new_code = "\n".join(new_code_lines)
        if new_code in chunk:
            return indent, False
    # sometimes llm returns code with trailing whitespace, if we have reached here check again but strip all trailing whitespace
    code_lines = [line.rstrip() for line in code.split("\n")]
    for indent in range(0, 40, 2):
        new_code_lines = [f"{' ' * indent}{line}" for line in code_lines]
        new_code = "\n".join(new_code_lines)
        if new_code in chunk:
            return indent, True
    return -1, False