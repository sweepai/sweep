from sweepai.utils.scorer import get_scores


def test_days_since_last_modified_scores():
    # Given: Two file score factors
    factors_recent_first = [(1, 10, 1), (1, 10, 30)]

    # When: We calculate scores
    scores_recent_first = get_scores(factors_recent_first)

    # Then: Verify the recent modification has a higher score
    assert scores_recent_first[0] > scores_recent_first[1]


def test_commit_count_effect_on_scores():
    # Given: Two file score factors with different commit counts but same modified days
    factors_commit_count = [(1, 10, 1), (1, 20, 1)]

    # When: We calculate scores
    scores_commit_count = get_scores(factors_commit_count)

    # Then: Verify the higher commit count has a higher score
    assert scores_commit_count[0] < scores_commit_count[1]
