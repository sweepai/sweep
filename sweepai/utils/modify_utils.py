from collections import defaultdict
from sweepai.config.client import SweepConfig

# post process rip grep output to be more condensed
def post_process_rg_output(root_directory: str, sweep_config: SweepConfig, output: str):
    processed_output = ""
    output_lines = output.split("\n")
    # empty lines are present at end of output
    output_lines = [line for line in output_lines if line]
    file_output_dict = defaultdict(list)
    for line in output_lines:
        filename, content = line.split(":", 1)
        filename = filename[len(root_directory) + 1:]
        if not sweep_config.is_file_excluded_aggressive(root_directory, filename):
            file_output_dict[filename].append(content)
    
    # determine if we need to truncate the output
    total_output_length = sum([len(line) for content in file_output_dict.values() for line in content])
    if total_output_length > 20000:
        for filename, content in file_output_dict.items():
            processed_output += f"File: {filename} had the following matching lines of code (some lines have been truncated):\n"
            if len(content) < 3:
                for line in content:
                    processed_output += f"{line}\n"
            else:
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
            processed_output += f"File: {filename} had the following matching lines of code:\n"
            for line in content:
                processed_output += f"{line}\n"
            processed_output += "\n"
    return processed_output