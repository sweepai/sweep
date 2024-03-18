import json
import os
from math import inf
from typing import Optional

import git
import pandas as pd
from datasets import load_dataset
from git import Repo
from loguru import logger
from rich import print
from rich.console import Console
from swe_bench_utils import get_files_to_change, run_modify_bot, run_search_test
from tqdm import tqdm

from sweepai.core.entities import Message
from sweepai.logn.cache import file_cache
from sweepai.utils.diff import generate_diff
from sweepai.utils.github_utils import MockClonedRepo

github_token = os.getenv("GITHUB_TOKEN")  # this is a github token with repo access
cprint = Console().print
CLONE_DIR = "/mnt/sweep_benchmark/tmp/repos"


# borrowed from ai-maintainer-inc / SWE-Bench-Runner
@file_cache()
def load_swebench_test_data(repo_name: Optional[str] = None) -> pd.DataFrame:
    """Load data from huggingface"""
    dataset = load_dataset("princeton-nlp/SWE-bench", "default", split="test")
    test_df = pd.DataFrame(dataset)
    test_df = test_df[
        [
            "instance_id",
            "created_at",
            "base_commit",
            "hints_text",
            "repo",
            "problem_statement",
            "patch",
            "test_patch",
        ]
    ]
    if repo_name:
        if repo_name not in test_df["repo"].unique():
            raise ValueError(
                f"repo_name {repo_name} not found in swebench test data. Please choose from {test_df['repo'].unique()}"
            )
        test_df = test_df[test_df["repo"] == repo_name]
    # sort the data by created_at starting with the oldest data
    test_df = test_df.sort_values(by=["created_at"], ascending=True)
    return test_df


# borrowed from ai-maintainer-inc / SWE-Bench-Runner
def checkout_or_clone_repo(repo_identifier: str, commit_hash: str) -> str:
    """
    Checks out the state of the repository prior to the specified commit.
    If the repo does not exist locally, it clones it first.

    Args:
        repo_identifier: Repository identifier in the format "owner/repo".
        commit_hash: The commit hash to check out.

    Returns:
        str: Absolute path to the repo directory.
    """
    repo_name = repo_identifier.split("/")[-1]
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN environment variable must be set.")
    # make the cloned dir if it doesn't exist
    os.makedirs(CLONE_DIR, exist_ok=True)
    repo_path = os.path.join(CLONE_DIR, repo_name)

    if os.path.exists(repo_path):
        repo = Repo(repo_path)
        repo.git.checkout("-f", commit_hash + "~1")
    else:
        repo_url = f"https://github.com/{repo_identifier}.git"
        repo = Repo.clone_from(repo_url, repo_path, env={"GITHUB_TOKEN": github_token})
        repo.git.checkout(commit_hash + "~1")

    return repo_path


cprint("Loading test data...", style="yellow")
test_data = load_swebench_test_data()
cprint("Loaded test data", style="green")

seed = 0
proportion = 0.25
test_data = test_data.sample(frac=proportion, random_state=seed)
name = "sweep-03-18-k-10"
output_file = f"{name}__SWE-bench_unassisted.jsonl"
search_results_file = f"eval/{name}-search_results.csv"
search_positions_file = f"eval/{name}-search_positions.txt"
logger.info(
    f"Loaded {len(test_data)} rows of test data ({proportion * 100}% of the total)"
)

open(search_results_file, "w").write("instance_id,mrr,acc\n")
open(search_positions_file, "w").write("instance_id,positions\n")

already_done_results = [json.loads(line) for line in open(output_file, "r").readlines()]
# already_done_results = []
previously_finished_tasks = set(
    [result["instance_id"] for result in already_done_results]
)

for i, row in tqdm(test_data.iterrows(), total=len(test_data)):
    instance_id = row.instance_id
    repo_identifier = row["repo"]
    commit_hash = row["base_commit"]
    problem_statement = row["problem_statement"]
    hints_text = row["hints_text"]
    solution_patch = row["patch"]
    print(
        repo_identifier,
        commit_hash,
        problem_statement.split("\n")[0],
        hints_text.split("\n")[0],
    )
    if instance_id in previously_finished_tasks:
        continue
    try:
        repo_path = checkout_or_clone_repo(repo_identifier, commit_hash)
        cloned_repo = MockClonedRepo.from_dir(
            repo_dir=repo_path,
            repo_full_name=repo_identifier,
            branch="main",
            git_repo=git.Repo(repo_path),
        )
        cloned_repo.git_repo.git.checkout("-f", commit_hash, force=True)
        resolution_files = []
        for line in solution_patch.splitlines():
            if line.startswith("---"):
                resolution_files.append(line.removeprefix("--- a/"))
        mrr, acc, rcm, positions = run_search_test(
            cloned_repo,
            problem_statement,
            commit_hash,
            k=15,
            resolution_files=resolution_files,
            name=instance_id,
        )
        with open(search_results_file, "a") as f:
            f.write(f"{instance_id},{mrr},{acc}\n")
        with open(search_positions_file, "a") as f:
            f.write(f"{instance_id},{positions}\n")
        fcrs, plan = get_files_to_change(
            rcm.current_top_snippets, problem_statement, repo_identifier
        )
        # continue
        # modify files
        additional_messages = [
            Message(
                role="user",
                content=f"""# Repo & Issue Metadata
Repo: {repo_identifier}
{problem_statement}""",
            ),
        ]
        combined_diff = ""
        updated_files = {}
        for fcr in fcrs:
            file_path = fcr.filename
            instructions = fcr.instructions
            try:
                file_contents = cloned_repo.git_repo.git.show(
                    f"{commit_hash}:{file_path}"
                )
                myfilepaths = [file for file in fcr.relevant_files]
                mymessages = [
                    f"<relevant_file file_path='{file}'>\n{open(repo_path + '/' + file).read()}\n</relevant_file>"
                    for file in fcr.relevant_files
                ]
                logger.info(f"{myfilepaths}")
                logger.info(f"{[len(m) for m in mymessages]}")
                updated_file = run_modify_bot(
                    code=file_contents,
                    instructions=instructions,
                    file_path=file_path,
                    start_line=0,
                    end_line=inf,
                    additional_messages=[
                        *additional_messages,
                        *[
                            Message(
                                role="user",
                                content=f"<relevant_file file_path='{file_path}'>\n{open(repo_path + '/' + file_path).read()}\n</relevant_file>",
                                key="instructions",
                            )
                            for file_path in fcr.relevant_files
                        ],
                    ],
                    relevant_filepaths=[
                        f"{repo_path}/{file}" for file in fcr.relevant_files
                    ],  # could be wrong
                    cloned_repo=cloned_repo,
                )
            except Exception as e:
                logger.error(f"Error modifying file {file_path} {e}")
                continue
            else:
                updated_files[file_path] = updated_file
                additional_messages.append(
                    Message(
                        role="user",
                        content=f"The following changes in {fcr.filename} have already been applied to address this problem:\n```\n"
                        + generate_diff(file_contents, updated_file)
                        + "\n```",
                    )
                )
        cloned_repo.git_repo.git.checkout(commit_hash, force=True)
        if updated_files:
            old_files = {}
            for file_path, updated_file in updated_files.items():
                full_file_path = os.path.join(repo_path, file_path)
                with open(full_file_path, "r") as f:
                    old_files[file_path] = f.read()
                with open(full_file_path, "w") as f:
                    f.write(updated_file)
            combined_diff = cloned_repo.git_repo.git.diff()
            for file_path, old_file in old_files.items():
                full_file_path = os.path.join(repo_path, file_path)
                with open(full_file_path, "w") as f:
                    f.write(old_file)
            print(
                f"Checked out {commit_hash} for repo {repo_identifier} at {repo_path}"
            )
        result = {
            "instance_id": instance_id,
            "model_name_or_path": name,
            "text": problem_statement,
            "full_output": combined_diff,
            "model_patch": combined_diff,
        }
        with open(output_file, "a") as f:
            f.write("\n" + json.dumps(result))
    except Exception as e:
        logger.exception(f"Exception occured while running the test: {e}")


# output a jsonl file in the format # call it sweep__SWE-bench_unassisted.jsonl
# instance_id = instance_id
# model_name_or_path = "sweep-03-15-unassisted"
# text = "filler_text"
# full_output = "filler_text"
# model_patch = "\n--- a/astroid/nodes/scoped_nodes.py\n+++ b/astroid/nodes/scoped_nodes.py\n@@ -100,7 +100,7 @@\n     if not isinstance(cls, ClassDef)"
# the patch is in the style of a git diff
# diff = difflib.unified_diff(original_text, modified_text, fromfile='original.txt', tofile='modified.txt')
