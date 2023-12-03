import pytest

from sweepai.agents.filter_agent import FilterAgent


def test_filter_search_query():
    filter_agent = FilterAgent()

    # Test with empty string
    original_query = ""
    expected_output = ""
    assert filter_agent.filter_search_query(original_query) == expected_output

    # Test with string containing only unnecessary terms
    original_query = "the and or"
    expected_output = ""
    assert filter_agent.filter_search_query(original_query) == expected_output

    # Test with string containing a mix of necessary and unnecessary terms
    original_query = "the quick brown fox"
    expected_output = "quick brown fox"
    assert filter_agent.filter_search_query(original_query) == expected_output
