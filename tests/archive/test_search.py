from sweepai.utils.search_and_replace import find_best_match

old_file = r"""
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
"""


target = """\
with open(file, "rb") as f:
    if len(f.read()) > 60000:
        return False\
"""

find_best_match(target, old_file)
