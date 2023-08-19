import os
import subprocess


def clone_repo(repo_url):
    subprocess.run(["git", "clone", repo_url])


def read_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            with open(file_path, "r") as f:
                print(f.read())


repo_url = "https://github.com/sweepai/sweep.git"
clone_repo(repo_url)
read_files("sweep")
