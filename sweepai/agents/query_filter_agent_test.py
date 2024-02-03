import pytest

from sweepai.agents.query_filter_agent import QueryFilterBot


def test_filter_query():
    bot = QueryFilterBot()

    # Test case 1: simple query
    query = "fix bug in function"
    filtered_query = bot.filter_query(query)
    assert filtered_query == "fix bug in function documentation"

    # Test case 2: query with unnecessary terms
    query = "fix the annoying bug in the function"
    filtered_query = bot.filter_query(query)
    assert filtered_query == "fix bug in function documentation"

    # Test case 3: query with technical jargon
    query = "resolve segmentation fault in function"
    filtered_query = bot.filter_query(query)
    assert filtered_query == "resolve segmentation fault in function documentation"
