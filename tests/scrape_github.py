import subprocess

cmd = "git log --no-merges -n 300 --pretty=format:'%s'"
result = subprocess.check_output(cmd, shell=True, text=True, cwd="/root/sweep/benchmark/data/repos/")


commits = result.split('\n')

for commit in set(commits):
    if "fix" in commit:
        print(commit)