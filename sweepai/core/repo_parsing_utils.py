import glob
import logging
import multiprocessing

# import multiprocessing
import os

from loguru import logger
from tqdm import tqdm

from sweepai.config.client import SweepConfig
from sweepai.core.entities import Snippet
from sweepai.utils.utils import Tiktoken, chunk_code

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
        if dir_name in file:
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
    with open(file, "r") as f:
        try:
            lines = f.readlines()
        except UnicodeDecodeError:
            logger.warning(f"UnicodeDecodeError: {file}, skipping")
            return False
        line_count = len(lines)
        data = "\n".join(lines)
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


FILE_THRESHOLD = 120


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
    file_list = glob.iglob(f"{directory}/**", recursive=True)
    file_list = [
        file_name
        for file_name in file_list
        if os.path.isfile(file_name)
        and filter_file(directory, file_name, sweep_config)
        and not is_dir_too_big(file_name)
    ]
    logger.info("Done reading files")
    all_chunks = []
    with multiprocessing.Pool(processes=multiprocessing.cpu_count() // 4) as pool:
        for chunks in tqdm(pool.imap(file_path_to_chunks, file_list)):
            all_chunks.extend(chunks)
    return all_chunks, file_list
