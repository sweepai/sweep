from sweepai.utils.github_utils import get_file_list

if __name__ == "__main__":
    for path in get_file_list("src"):
        print(path)
