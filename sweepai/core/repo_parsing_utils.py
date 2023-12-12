import glob
import multiprocessing
import os
import logging

from tqdm import tqdm

from sweepai.config.client import SweepConfig
from sweepai.core.entities import Snippet
from sweepai.logn import logger
from sweepai.logn.cache import file_cache
from sweepai.utils.utils import chunk_code


def filter_file(directory, file, sweep_config: SweepConfig):
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
    try:
        if os.stat(file).st_size > 240000:
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

    return True


def read_file(file_name):
    try:
        with open(file_name, "r") as f:
            return f.read()
    except SystemExit:
        raise SystemExit
    except:
        return ""

FILE_THRESHOLD = 100

def file_path_to_chunks(file_path: str):
    file_contents = read_file(file_path)
    chunks = chunk_code(file_contents, path=file_path)
    return chunks

@file_cache()
def repo_to_chunks(
    directory: str, sweep_config: SweepConfig
) -> tuple[list[Snippet], list[str]]:
    dir_file_count = {}

    def is_dir_too_big(file_name):
        dir_name = os.path.dirname(file_name)
        only_file_name = os.path.basename(dir_name)
        if (
            only_file_name in ("node_modules", "venv", "patch")
        ):
            return True
        if dir_name not in dir_file_count:
            dir_file_count[dir_name] = len(os.listdir(dir_name))
        return dir_file_count[dir_name] > FILE_THRESHOLD

    logger.info(f"Reading files from {directory}")
    file_list = glob.iglob(f"{directory}/**", recursive=True)
    
    file_list = [
        file_name
        for file_name in file_list
        if filter_file(directory, file_name, sweep_config)
        and not is_dir_too_big(file_name)
    ]
    all_chunks = []
    with multiprocessing.Pool(processes=8) as pool:
        for chunks in pool.imap(file_path_to_chunks, file_list):
            all_chunks.extend(chunks)
    return all_chunks, file_list
