import json
import time
import os
from github import Github
import datetime
import sys

from fastapi.testclient import TestClient

from sweepai.api import app, global_threads

g = Github(os.environ["GITHUB_PAT"])
repo_name = "sweepai/e2e" # for e2e test this is hardcoded
repo = g.get_repo(repo_name)

if __name__ == "__main__":
    print("got repo", g)
    print("env was", os.environ["GITHUB_PAT"])
