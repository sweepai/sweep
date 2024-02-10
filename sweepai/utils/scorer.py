from datetime import datetime


def compute_score(relative_file_path, git_repo):
    commits = list(git_repo.iter_commits(paths=relative_file_path))
    score_factor = get_factors(commits)
    return score_factor


def get_factors(commits):
    commit_count = len(commits) + 1
    earliest_commit = commits[0].committed_datetime if commits else datetime.now()
    current_time = datetime.now()
    tz_info = earliest_commit.astimezone().tzinfo
    if tz_info:
        current_time = datetime.now().astimezone(tz_info)
        earliest_commit = earliest_commit.astimezone(tz_info)
    days_since_last_modified = (
        max(
            ((current_time - earliest_commit).total_seconds() // 3600),
            0,
        )
        + 1
    )
    return (1, commit_count, days_since_last_modified)


def convert_to_percentiles(values, max_percentile=0.25):
    sorted_values = sorted(values)  # Sort the values in ascending order
    n = len(sorted_values)
    percentile_mapping = {
        value: (i / (n)) * max_percentile for i, value in enumerate(sorted_values)
    }
    percentiles = [
        percentile_mapping[value] for value in values
    ]  # Create the percentiles list based on the mapping

    return percentiles


def get_scores(score_factors):
    # add all of the arrays together
    line_count_scores = [x[0] for x in score_factors]
    commit_count_scores = [x[1] for x in score_factors]
    days_since_last_modified_scores = [x[2] for x in score_factors]
    line_count_scores = convert_to_percentiles(line_count_scores, 1)
    commit_count_scores = convert_to_percentiles(commit_count_scores, 1)
    days_since_last_modified_scores = convert_to_percentiles(
        days_since_last_modified_scores, 1
    )
    days_since_last_modified_scores = [1 - score for score in days_since_last_modified_scores]
    scores = [
        sum(x)
        for x in zip(
            line_count_scores, commit_count_scores, days_since_last_modified_scores
        )
    ]
    return convert_to_percentiles(scores, 0.25)


# section id="unit_tests"
import pytest


def test_days_since_last_modified_scores():
    # Given: Two file score factors
    factors_recent = [(1, 10, 1), (1, 10, 1)]  # Recently modified
    factors_older = [(1, 10, 30), (1, 10, 30)]  # Older modification

    # When: We calculate scores
    scores_recent = get_scores(factors_recent)
    scores_older = get_scores(factors_older)

    # Then: Verify the recent modification has a higher score
    assert scores_recent[0] > scores_older[0]


def test_commit_count_effect_on_scores():
    # Given: Two file score factors with different commit counts but same modified days
    factors_high_commit = [(1, 20, 10), (1, 20, 10)]  # Higher commit count
    factors_low_commit = [(1, 5, 10), (1, 5, 10)]  # Lower commit count

    # When: We calculate scores
    scores_high_commit = get_scores(factors_high_commit)
    scores_low_commit = get_scores(factors_low_commit)

    # Then: Verify the file with higher commit count has a higher score
    assert scores_high_commit[0] > scores_low_commit[0]
