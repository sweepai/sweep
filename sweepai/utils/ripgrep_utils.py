
from sweepai.config.client import SweepConfig

# post process rip grep output to be more condensed
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
    processed_output = ""
    output_lines = output.split("\n")
    # empty lines are present at end of output
    output_lines = [line for line in output_lines if line]
    file_output_dict = {}
    file_to_num_occurrences = {}
    for line in output_lines:
        filename, content = line.split(":", 1)
        filename = filename[len(root_directory) + 1:]
        if not sweep_config.is_file_excluded_aggressive(root_directory, filename):
            if filename not in file_output_dict:
                file_output_dict[filename] = ""
            file_output_dict[filename] += (content + "\n")
            if filename not in file_to_num_occurrences:
                file_to_num_occurrences[filename] = 0
            file_to_num_occurrences[filename] += 1
    
    # determine if we need to truncate the output
    total_output_length = sum([len(line) for content in file_output_dict.values() for line in content])
    file_name_and_contents = [(filename, content) for filename, content in file_output_dict.items()]
    file_name_and_contents.sort(key=lambda x: x[0])
    if total_output_length > sweep_config.truncation_cutoff:
        for filename, content in file_name_and_contents:
            processed_output += f"File: {filename} contained the following matching lines of code"
            content = content.split("\n")
            if len(content) < 4:
                processed_output += " :\n"
                for line in content:
                    processed_output += f"{line}\n"
            else:
                processed_output += " (truncated):\n"
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
        for filename, content in file_name_and_contents:
            processed_output += f"File: {filename} contained the following matching lines of code:\n" + content + "\n"
    return processed_output, file_output_dict, file_to_num_occurrences

def cleaned_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
    results = {}
    for block in output.split("\n\n"):
        if not block.strip():
            continue
        full_file_path, *contents = block.split("\n")
        file_path = full_file_path[len(root_directory) + 1:]
        if sweep_config.is_file_excluded_aggressive(root_directory, file_path):
            continue
        results[file_path.removeprefix(root_directory).removeprefix("/")] = "\n".join(contents)
    return results

# try and find code_snippet inside file_contents given various levels of indentation, and right strip the lines of code
# if successful returns the num of spaces required to find the code match and if we need to rstrip the old code or not
def manual_code_check(file_contents: str, code_snippet: str) -> tuple[int, bool]:
    code_lines = [line for line in code_snippet.split("\n")]
    # special case for single line
    if len(code_lines) == 1:
        file_lines = file_contents.split("\n")
        # check directly
        new_code = code_lines[0]
        # only continue if it is unique, this will then later fail the uniqueness check
        if file_contents.count(new_code) > 1:
            return 0, False
        if new_code in file_contents:
            # now check how many leading whitespaces there are
            for line in file_lines:
                if new_code in line:
                    # unless the code is at the start of the line
                    if line.startswith(new_code):
                        return 0, False
                    return len(line)-len(line.lstrip()), False
        else:
            # now try rstrip if initially the code is not there
            new_code = new_code.rstrip()
            if file_contents.count(new_code) > 1: # uniqueness check
                return 0, False
            if new_code in file_contents:
               # now check how many leading whitespaces there are
                for line in file_lines:
                    if new_code in line:
                        # unless the code is at the start of the line
                        if line.startswith(new_code):
                            return 0, True
                        return len(line)-len(line.lstrip()), True
        return -1, False
                
    # assume one indent is two spaces and check max 10 indents
    for indent in range(0, 40, 2):
        new_code_lines = [f"{' ' * indent}{line}" if line.strip() else "" for line in code_lines]
        new_code = "\n".join(new_code_lines)
        if new_code in file_contents:
            return indent, False
    # sometimes llm returns code with trailing whitespace, if we have reached here check again but strip all trailing whitespace
    code_lines = [line.rstrip() for line in code_snippet.split("\n")]
    for indent in range(0, 40, 2):
        new_code_lines = [f"{' ' * indent}{line}" if line.strip() else "" for line in code_lines]
        new_code = "\n".join(new_code_lines)
        if new_code in file_contents:
            return indent, True
    return -1, False

# splits the output of ripgrep into a line number and the rest of the code line
def parse_ripgrep_line(line: str):
    if ":" not in line:
        return -1, ""
    line_number, code_line = line.split(":", 1)
    return int(line_number), code_line