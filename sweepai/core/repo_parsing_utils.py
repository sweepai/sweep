import glob
import os
import itertools

from sweepai.entrypoints.chunker import chunk_code


def filter_file(file, sweep_config):
    for ext in sweep_config.exclude_exts:
        if file.endswith(ext):
            return False
    for dir_name in sweep_config.exclude_dirs:
        if file[len("repo/") :].startswith(dir_name):
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

    with open(file, "rb") as f:
        if len(f.read()) > 60000:
            return False
    return True


def read_file(file_name):
    try:
        with open(file_name, "r") as f:
            return f.read()
    except:
        return ""


def repo_to_chunks(sweep_config):
    file_list = glob.iglob("repo/**", recursive=True)
    file_list = [
        file_name for file_name in file_list if filter_file(file_name, sweep_config)
    ]
    all_chunks = []
    for file_path in file_list:
        file_contents = read_file(file_path)
        chunks = chunk_code(file_contents, path=file_path)
        all_chunks.extend(chunks)
    return all_chunks, file_list
