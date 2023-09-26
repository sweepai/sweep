from sweepai.utils.github_utils import list_directory_tree

if __name__ == "__main__":
    tree = list_directory_tree(
        "sweepai",
        included_files=["core/chat.py", "utils/utils.py"],
        included_directories=["core", "utils"],
    )
    print(tree)
