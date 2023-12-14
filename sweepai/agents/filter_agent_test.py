import pytest

from sweepai.agents.filter_agent import FilterBot


def test_filter_query():
    bot = FilterBot()

    # Test case: query with unnecessary terms
    query = "How to sort a list in Python"
    expected_output = ["sort", "list", "Python"]
    assert bot.filter_query(query) == expected_output

    # Test case: query without unnecessary terms
    query = "sort list Python"
    expected_output = ["sort", "list", "Python"]
    assert bot.filter_query(query) == expected_output

    # Test case: empty query
    query = ""
    expected_output = []
    assert bot.filter_query(query) == expected_output
