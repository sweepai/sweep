import os

from loguru import logger
from tqdm import tqdm
from sweepai.config.client import SweepConfig
from sweepai.core.repo_parsing_utils import FILE_THRESHOLD, filter_file
from sweepai.utils.github_utils import ClonedRepo, get_installation_id
from sweepai.utils.timer import Timer


if __name__ == "__main__":
    REPO_FULL_NAME = os.environ.get("REPO_FULL_NAME")
    sweep_config = SweepConfig()
    installation_id = get_installation_id(REPO_FULL_NAME.split("/")[0])
    cloned_repo = ClonedRepo(REPO_FULL_NAME, installation_id, "master")
    # filter all of the files
    directory = cloned_repo.repo_dir
    logger.info(f"Reading files from {directory}")
    vis = set()

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
        ]
    file_list = [file.split(directory)[1] for file in file_list]

    def render_directory_tree(file_list):
        tree = {}
        for path in file_list:
            parts = path.split('/')
            current = tree
            for part in parts:
                current = current.setdefault(part, {})

        def render_tree(node, level=0):
            dir_tree_string = ""
            for key, value in node.items():
                dir_tree_string += "  " * level + key + "\n"
                dir_tree_string += render_tree(value, level + 1)
            return dir_tree_string

        return render_tree(tree).strip()
    print(render_directory_tree(file_list))
    breakpoint()