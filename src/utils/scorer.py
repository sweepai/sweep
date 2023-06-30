
from datetime import datetime

def compute_score(contents, commits):
    line_count = contents.count("\n") 
    if line_count > 30:
        line_count_score = 2
    else:
        line_count_score = line_count / 15
    commit_count = len(commits)
    commit_count = 1 if commit_count < 3 else commit_count / 3
    days_since_last_modified = (datetime.now() - commits[0].commit.author.date).days + 1
    if days_since_last_modified > 14:
        days_since_last_modified_score = 7 / days_since_last_modified
    elif days_since_last_modified <= 4:
        days_since_last_modified_score = 2
    else:
        days_since_last_modified_score = 10 / days_since_last_modified
    return (line_count_score * commit_count * days_since_last_modified_score)