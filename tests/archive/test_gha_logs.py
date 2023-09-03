import io
import os
import zipfile
import requests
from loguru import logger


def get_dirs(zipfile: zipfile.ZipFile):
    return [file for file in zipfile.namelist() if file.endswith("/") and "/" in file]


def get_files_in_dir(zipfile: zipfile.ZipFile, dir: str):
    return [
        file
        for file in zipfile.namelist()
        if file.startswith(dir) and not file.endswith("/")
    ]


def download_logs(repo_full_name: str, run_id: int):
    # token = os.environ.get("GITHUB_PAT")
    # headers = {
    #     "Accept": "application/vnd.github+json",
    #     "Authorization": f"Bearer {token}",
    #     "X-GitHub-Api-Version": "2022-11-28"
    # }
    # response = requests.get(f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs", headers=headers)

    logs_str = ""
    # if response.status_code == 200:
    if True:
        # this is the worst code I've ever written. I'm sorry.
        # content = response.content
        content = open("/home/kevin/Downloads/logs_2464.zip", "rb").read()
        zip_file = zipfile.ZipFile(io.BytesIO(content))
        dirs = get_dirs(zip_file)

        # for directory in dirs:
        #     files = get_files_in_dir(zip_file, directory)
        #     numbers = [int(file[len(directory):file.find("_")]) for file in files]
        #     for i in range(1, 100):
        #         if i not in numbers:
        #             break
        #     i -= 1
        #     target_file = ""
        #     for file in files:
        #         if file[len(directory): file.find("_")] == str(i):
        #             target_file = file
        #             break
        #     else:
        #         raise ValueError("No file found")
        #     print(target_file)
        #     with zip_file.open(target_file) as f:
        #         logs_str += f.read().decode("utf-8")
        for file in zip_file.namelist():
            if file.endswith(".txt"):
                with zip_file.open(file) as f:
                    logs = f.read().decode("utf-8")
                    last_line = logs.splitlines()[-1]
                    if "##[error]" in last_line:
                        logs_str += logs
    else:
        # logger.info(response.text)
        logger.warning(f"Failed to download logs for run id: {run_id}")
    return logs_str


def clean_logs(logs_str: str):
    # Extraction process could be better
    MAX_LINES = 300
    log_list = logs_str.split("\n")
    truncated_logs = [log[log.find(" ") + 1 :] for log in log_list]
    patterns = [
        # for docker
        "Already exists",
        "Pulling fs layer",
        "Waiting",
        "Download complete",
        "Verifying Checksum",
        "Pull complete",
        # For github
        "remote: Counting objects",
        "remote: Compressing objects:",
        "Receiving objects:",
        "Resolving deltas:",
        "[command]/usr/bin/git ",
        "Download action repository",
        # For python
        "Collecting",
        "Downloading",
        "Installing",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        # For prettier
        "npm WARN EBADENGINE ",
        "npm WARN deprecated ",
        "prettier/prettier",
    ]
    cleaned_lines = [
        log.strip()
        for log in truncated_logs
        if not any(log.strip().startswith(pattern) for pattern in patterns)
    ]
    return "\n".join(cleaned_lines[: min(MAX_LINES, len(cleaned_lines))])


import timeit
import tempfile
from sweepai.core.sweep_bot import SweepBot

def old_check_completion(file_name: str, new_content: str) -> bool:
    # Old implementation for benchmarking
    with open(file_name, "rb") as f:
        if len(f.read()) > 60000:
            return False
    return True

def test_check_completion():
    # Create a temporary file of known size
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(b'a' * 50000)
        temp_name = temp.name

    bot = SweepBot()

    # Test the new implementation
    assert bot.check_completion(temp_name, "") == True

    # Create a larger file
    with open(temp_name, "wb") as temp:
        temp.write(b'a' * 70000)

    # Test the new implementation
    assert bot.check_completion(temp_name, "") == False

    os.remove(temp_name)

def benchmark():
    # Create a temporary file of known size
    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(b'a' * 70000)
        temp_name = temp.name

    bot = SweepBot()

    # Benchmark the old implementation
    old_time = timeit.timeit(lambda: old_check_completion(temp_name, ""), number=1000)
    print(f"Old implementation time: {old_time}")

    # Benchmark the new implementation
    new_time = timeit.timeit(lambda: bot.check_completion(temp_name, ""), number=1000)
    print(f"New implementation time: {new_time}")

    os.remove(temp_name)

if __name__ == "__main__":
    run_id = 5753755655
    print(clean_logs(download_logs("sweepai/sweep", run_id)))
    test_check_completion()
    benchmark()
