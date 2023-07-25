import math
from datetime import datetime


def get_factors(contents: str,
                commits: list):
    line_count = contents.count("\n")
    if line_count > 200:
        line_count_score = 10
    else:
        line_count_score = line_count / 20
    commit_count = len(commits) + 1
    days_since_last_modified = max(((datetime.now() - commits[0].commit.author.date).total_seconds() // 3600), 0) + 1
    return (line_count_score, commit_count, days_since_last_modified)

def get_scores(score_factors):
    # add all of the arrays together
    line_count_scores = [x[0] for x in score_factors]
    commit_count_scores = [x[1] for x in score_factors]
    days_since_last_modified_scores = [x[2] for x in score_factors]
    line_count_scores = convert_to_percentiles(line_count_scores, 1)
    commit_count_scores = convert_to_percentiles(commit_count_scores, 1)
    days_since_last_modified_scores = convert_to_percentiles(days_since_last_modified_scores, 1)
    scores = [sum(x) for x in zip(line_count_scores, commit_count_scores, days_since_last_modified_scores)]
    return convert_to_percentiles(scores, 0.1)

def convert_to_percentiles(values, max_percentile=0.1):
    sorted_values = sorted(values)  # Sort the values in ascending order
    n = len(sorted_values)
    percentile_mapping = {value: (i / (n)) * max_percentile for i, value in enumerate(sorted_values)}
    percentiles = [percentile_mapping[value] for value in values]  # Create the percentiles list based on the mapping

    return percentiles
