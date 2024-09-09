import os
import subprocess
import sys

def test_run_file_tests():
    list_of_files = ["sweepai/core/repo_parsing_utils.py", "sweepai/utils/github_utils.py", "sweepai/agents/modify_file.py", "sweepai/core/context_pruning.py", "sweepai/agents/modify_bot.py"]

    for file in list_of_files:
        print(f"Running file: {file}")
        commands = ["python", f"{file}"]
        result = subprocess.run(" ".join(commands), capture_output=True, text=True, shell=True)
        error_message = f"{file.split(os.path.sep)[-1]} failed"
        if error_message in result.stderr:
            sys.exit(f"Error in file: {file}\n{result.stderr}")

if __name__ == "__main__":
    test_run_file_tests()
