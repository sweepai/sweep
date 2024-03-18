import os
import subprocess
import sys

def test_run_file_tests():
    list_of_files = ["sweepai/core/repo_parsing_utils.py", "sweepai/utils/github_utils.py", "sweepai/agents/modify_file.py", "sweepai/core/context_pruning.py", "sweepai/agents/modify_bot.py"]

    for file in list_of_files:
        print(f"Running file: {file}")
        result = subprocess.run(["python", f"{file}"], capture_output=True, text=True)
        error_message = f"{file.split(os.path.sep)[-1]} failed"
        if error_message in result.stderr:
            print(f"Error in file: {file}")
            sys.exit(1)

if __name__ == "__main__":
    test_run_file_tests()
