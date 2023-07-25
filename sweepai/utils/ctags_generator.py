import os
from ctags import Ctags

def generate_ctags(file_path):
    """
    Generate ctags for a given file.

    Args:
        file_path (str): The path to the file.

    Returns:
        str: The generated ctags.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No such file: '{file_path}'")

    ctags = Ctags(file_path)
    tags = ctags.run_ctags()

    return tags