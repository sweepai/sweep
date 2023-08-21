import os
import subprocess


def check_git_installation():
    try:
        subprocess.run(["git", "--version"], check=True)
    except subprocess.CalledProcessError:
        print("Git is not installed. Please install git and try again.")
        exit(1)


def clone_repo():
    try:
        subprocess.run(
            ["git", "clone", "https://github.com/sweepai/sweep.git"], check=True
        )
    except subprocess.CalledProcessError:
        print(
            "Failed to clone the repository. Please check your internet connection and try again."
        )
        exit(1)


def read_files():
    for root, dirs, files in os.walk("./sweep"):
        for file in files:
            with open(os.path.join(root, file), "r") as f:
                print(f.read())


if __name__ == "__main__":
    check_git_installation()
    clone_repo()
    read_files()
