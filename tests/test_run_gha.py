import random
from time import sleep
from github import GithubException
from github.Repository import Repository
from sweepai.config.server import INSTALLATION_ID
from sweepai.handlers.on_check_suite import download_logs
from sweepai.utils.github_utils import get_github_client

# given a branch, run a github action on a sub-branch and then get the logs

original_gha_file = "sweep.yml"

command = """echo "Hello, World!"
echo "This is a multi-line command."
ls -l
pwd"""

branch_name = "feat/test-gha"
REPO_FULL_NAME = "sweepai/sweep"
run_name = 'code-quality (3.10, ubuntu-latest)'

def run_gha_on_branch(run_name, original_gha_file, original_branch_name, command, repo: Repository) -> int:
    # Create a new branch
    new_branch_name = f"{original_branch_name}-run"
    # get last page of branches
    existing_branches = [branch.name for branch in repo.get_branches()[:40]] # only get the last 40 branches
    for _ in range(1, 10):
        # generate random short hash
        run_hash = hex(random.getrandbits(32))[2:]
        new_branch_name = f"{original_branch_name}-run-{run_hash}"
        if new_branch_name not in existing_branches:
            try:
                repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=repo.get_branch(original_branch_name).commit.sha)
                break
            except GithubException as e:
                if e.status == 422:  # Branch already exists
                    print(f"Branch {new_branch_name} already exists. Skipping branch creation.")
                else:
                    raise e

    # Update the GitHub Action file with the command
    gha_file_path = f".github/workflows/{original_gha_file}"
    content = repo.get_contents(gha_file_path, ref=original_branch_name)
    gha_content = content.decoded_content.decode("utf-8")
    # get the whitespace before placeholder
    line_with_placeholder = [line for line in gha_content.split("\n") if 'echo "Placeholder"' in line][0]
    whitespace = line_with_placeholder.split('echo "Placeholder"')[0]
    command = command.replace("\n", f"\n{whitespace}")
    updated_gha_content = gha_content.replace('echo "Placeholder"', command)
    repo.update_file(
        path=gha_file_path,
        message=f"Update GitHub Action for branch {new_branch_name}",
        content=updated_gha_content,
        sha=content.sha,
        branch=new_branch_name,
    )
    # get the commit's pending runs
    commit = repo.get_commit(sha=repo.get_branch(new_branch_name).commit.sha)
    sleep(20) # wait for the commit to be processed
    runs = commit.get_check_runs()  

    # wait for the run to complete
    cnt = 0
    while any(run.conclusion not in ["success", "failure"] for run in runs) or cnt < 10:
        runs = commit.get_check_runs()
        # get the run corresponding to the original gha file
        breakpoint()
        run = [run for run in runs if run.name == run_name][0]
        if run.conclusion in ["success", "failure"]:
            return run.id
        cnt += 1
        sleep(5)
    breakpoint()

    return None

_, g = get_github_client(INSTALLATION_ID)
# Get the repository
repo = g.get_repo(REPO_FULL_NAME)

# RUN_ID = run_gha_on_branch(run_name=run_name, original_gha_file=original_gha_file, original_branch_name=branch_name, command=command, repo=repo)
RUN_ID = 8742470593 # needs to be a different run id

logs = download_logs(repo_full_name=REPO_FULL_NAME, run_id=RUN_ID, installation_id=INSTALLATION_ID, get_errors_only=False)
breakpoint()