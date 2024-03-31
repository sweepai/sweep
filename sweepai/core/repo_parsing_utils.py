
import logging
import multiprocessing

# import multiprocessing
import os

from loguru import logger
from tqdm import tqdm

from sweepai.config.client import SweepConfig
from sweepai.core.entities import Snippet
from sweepai.utils.file_utils import read_file_with_fallback_encodings
from sweepai.utils.utils import Tiktoken, chunk_code
from sweepai.utils.timer import Timer

tiktoken_client = Tiktoken()


def filter_file(directory: str, file: str, sweep_config: SweepConfig) -> bool:
    """
    Check if a file should be filtered based on its size and other criteria.

    Args:
        file (str): The path to the file.
        sweep_config (SweepConfig): The configuration object.

    Returns:
        bool: True if the file should be included, False otherwise.
    """
    for ext in sweep_config.exclude_exts:
        if file.endswith(ext):
            return False
    for dir_name in sweep_config.exclude_dirs:
        if file[len(directory) + 1 :].startswith(dir_name):
            return False
    for dir_name in sweep_config.exclude_path_dirs:
        file_parts = file.split(os.path.sep)
        if dir_name in file_parts:
            return False
    try:
        if os.stat(file).st_size > 240000:
            return False
        if os.stat(file).st_size < 10:
            return False
    except FileNotFoundError as e:
        logging.error(f"File not found: {file}. Error: {e}")
        return False
    if not os.path.isfile(file):
        return False
    with open(file, "rb") as f:
        is_binary = False
        for block in iter(lambda: f.read(1024), b""):
            if b"\0" in block:
                is_binary = True
                break
        if is_binary:
            return False
        f.close()
    try:
        # fetch file
        data = read_file_with_fallback_encodings(file)
        lines = data.split("\n")
    except UnicodeDecodeError:
        logger.warning(f"UnicodeDecodeError: {file}, skipping")
        return False
    line_count = len(lines)
    # if average line length is greater than 200, then it is likely not human readable
    if len(data)/line_count > 200:
        return False
    # check token density, if it is greater than 2, then it is likely not human readable
    token_count = tiktoken_client.count(data)
    if token_count == 0:
        return False
    if len(data)/token_count < 2:
        return False
    return True


def read_file(file_name: str) -> str:
    try:
        with open(file_name, "r") as f:
            return f.read()
    except SystemExit:
        raise SystemExit
    except Exception:
        return ""


FILE_THRESHOLD = 240


def file_path_to_chunks(file_path: str) -> list[str]:
    file_contents = read_file(file_path)
    chunks = chunk_code(file_contents, path=file_path)
    return chunks


# @file_cache()
def directory_to_chunks(
    directory: str, sweep_config: SweepConfig
) -> tuple[list[Snippet], list[str]]:
    dir_file_count = {}

    def is_dir_too_big(file_name):
        dir_name = os.path.dirname(file_name)
        only_file_name = os.path.basename(dir_name)
        if only_file_name in ("node_modules", "venv", "patch"):
            return True
        if dir_name not in dir_file_count:
            dir_file_count[dir_name] = len(os.listdir(dir_name))
        return dir_file_count[dir_name] > FILE_THRESHOLD

    logger.info(f"Reading files from {directory}")
    vis = set()
    def dfs(file_path: str = directory):
        only_file_name = os.path.basename(file_path)
        if only_file_name in ("node_modules", "venv", "patch"):
            return
        if file_path in vis:
            return
        vis.add(file_path)
        if os.path.isdir(file_path):
            for file_name in os.listdir(file_path):
                for sub_file_path in dfs(os.path.join(file_path, file_name)):
                    yield sub_file_path
        else:
            yield file_path
    with Timer() as timer:
        file_list = dfs()
        file_list = [
            file_name
            for file_name in file_list
            if filter_file(directory, file_name, sweep_config)
            and os.path.isfile(file_name)
            and not is_dir_too_big(file_name)
        ]
    logger.info("Done reading files")
    all_chunks = []
    with multiprocessing.Pool(processes=multiprocessing.cpu_count() // 4) as pool:
        for chunks in tqdm(pool.imap(file_path_to_chunks, file_list), total=len(file_list)):
            all_chunks.extend(chunks)
    return all_chunks, file_list

if __name__ == "__main__":
    try:
        from sweepai.utils.github_utils import ClonedRepo, get_installation_id
        organization_name = "sweepai"
        
        installation_id = get_installation_id(organization_name)
        cloned_repo = ClonedRepo("sweepai/sweep", installation_id, "main")
        sweep_config = SweepConfig()
        chunks, file_list = directory_to_chunks(cloned_repo.repo_dir, sweep_config)
        # ensure no unallowed files are let through
        assert(not any([file for file in file_list if sweep_config.is_file_excluded(file)]))
        # pick 10 random files and turn them to chunks
        import random
        for _ in range(10):
            idx = random.randint(0, len(file_list) - 1)
            file_chunks = file_path_to_chunks(file_list[idx])

    except Exception as e:
        logger.error(f"repo_parsing_utils.py failed to run successfully with error: {e}")
