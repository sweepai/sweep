import math
from datetime import datetime


def compute_score(contents, commits, file_age_in_days):
    MAX_FILE_AGE = 60
    MAX_COMMIT_COUNT = 30
    line_count = contents.count("\n")
    if line_count > 200:
        line_count_score = 10
    else:
        line_count_score = line_count / 20
    commit_count = (min(len(commits), MAX_COMMIT_COUNT) + 1) // 3
    days_since_last_modified = max(((datetime.now() - commits[0].commit.author.date).total_seconds() // 3600), 0) + 1
    if file_age_in_days >= MAX_FILE_AGE:
        age_factor = 6
    else:
        age_factor = (file_age_in_days // 10) + 1
    return (line_count_score * commit_count / days_since_last_modified) * age_factor


def convert_to_percentiles(values):
    sorted_values = sorted(values)  # Sort the values in ascending order
    n = len(sorted_values)
    max_percentile = .1
    percentile_mapping = {value: (i / (n)) * max_percentile for i, value in enumerate(sorted_values)}
    percentiles = [percentile_mapping[value] for value in values]  # Create the percentiles list based on the mapping

    return percentiles
