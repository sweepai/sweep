from hashlib import md5
import multiprocessing

import os

from loguru import logger
from tqdm import tqdm

from sweepai.config.client import SweepConfig
from sweepai.config.server import CACHE_DIRECTORY
from sweepai.core.entities import Snippet
from sweepai.utils.file_utils import read_file_with_fallback_encodings
from sweepai.utils.tiktoken_utils import Tiktoken
from sweepai.utils.code_validators import chunk_code
from sweepai.utils.timer import Timer
from diskcache import Cache

chunk_cache = Cache(f'{CACHE_DIRECTORY}/chunk_cache') # we instantiate a singleton, diskcache will handle concurrency
file_name_cache = Cache(f'{CACHE_DIRECTORY}/file_name_cache')

tiktoken_client = Tiktoken()

def filter_file(directory: str, file: str, sweep_config: SweepConfig) -> bool:
    cache_key = directory + file
    if cache_key in file_name_cache:
        return file_name_cache[cache_key]
    result = _filter_file(directory, file, sweep_config)
    file_name_cache[cache_key] = result
    return result

def _filter_file(directory: str, file: str, sweep_config: SweepConfig) -> bool:
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
    only_file_name = file[len(directory) + 1 :]
    only_file_name_parts = only_file_name.split(os.path.sep)
    for dir_name in sweep_config.exclude_dirs:
        for file_part in only_file_name_parts[:-1]:
            if file_part == dir_name:
                return False
    for dir_name in sweep_config.exclude_path_dirs:
        if dir_name in only_file_name_parts:
            return False
    try:
        size = os.stat(file).st_size
        if size > 240000 or size < 10:
            return False
    except FileNotFoundError as e:
        logger.info(f"File not found: {file}. {e}")
        return False
    if not os.path.isfile(file):
        return False
    try:
        data = read_file_with_fallback_encodings(file)
    except UnicodeDecodeError:
        logger.warning(f"UnicodeDecodeError: {file}, skipping")
        return False
    if b'\x00' in data.encode():
        return False
    line_count = data.count("\n") + 1
    # if average line length is greater than 200, then it is likely not human readable
    if len(data) / line_count > 200:
        return False
    # check token density, if it is greater than 2, then it is likely not human readable
    token_count = tiktoken_client.count(data[:1000])
    if token_count == 0:
        return False
    if len(data[:1000]) / token_count < 2 and len(data) > 100:
        return False
    return True

def read_file(file_name: str) -> str:
    try:
        with open(file_name, "r") as f:
            return f.read()
    except Exception:
        return ""


FILE_THRESHOLD = 240

def conditional_hash(contents: str):
    if len(contents) > 255:
        return md5(contents.encode()).hexdigest()
    return contents

def file_path_to_chunks(file_path: str) -> list[str]:
    file_contents = read_file(file_path)
    content_hash = conditional_hash(file_path + file_contents)
    if content_hash in chunk_cache:
        return chunk_cache[content_hash]
    chunks = chunk_code(file_contents, path=file_path)
    chunk_cache[content_hash] = chunks
    return chunks


# @file_cache()
def directory_to_chunks(
    directory: str, sweep_config: SweepConfig, do_not_use_file_cache: bool = False,
) -> tuple[list[Snippet], list[str]]:
    # dir_file_count = {}

    logger.info(f"Reading files from {directory}")
    vis = set()
    # 81.5s -> 42.68
    def dfs(file_path: str = directory):
        only_file_name = os.path.basename(file_path)
        if only_file_name in ("node_modules", ".venv", "build", "venv", "patch"):
            return
        if file_path in vis:
            return
        vis.add(file_path)
        try:
            with os.scandir(file_path) as it:
                children = list(it)
                if len(children) > FILE_THRESHOLD:
                    return
                for entry in children:
                    if entry.is_dir(follow_symlinks=False):
                        yield from dfs(entry.path)
                    else:
                        yield entry.path
        except NotADirectoryError:
            yield file_path
    with Timer():
        file_list = dfs()
        file_list = [
            file_name
            for file_name in tqdm(file_list)
            if filter_file(directory, file_name, sweep_config)
            # and os.path.isfile(file_name) # should be unneeded
        ]
    logger.info("Done reading files")
    all_chunks = []
    with multiprocessing.Pool(processes=multiprocessing.cpu_count() // 4) as pool:
        for chunks in tqdm(pool.imap(file_path_to_chunks, file_list), total=len(file_list), desc="Chunking files"):
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
