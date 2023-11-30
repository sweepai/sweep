import pytest

from sweepai.agents.query_filter_agent import QueryFilterAgent


@pytest.fixture
def query_filter_agent():
    return QueryFilterAgent()

def test_filter_query(query_filter_agent):
    test_cases = [
        ("This is a simple query", "simple query"),
        ("A more complex query with unnecessary terms", "complex query"),
        ("", ""),
        ("Query with special characters!@#$%^&*()", "Query special characters"),
        ("Query with numbers 1234567890", "Query numbers"),
    ]

    for original_query, expected_query in test_cases:
        assert query_filter_agent.filter_query(original_query) == expected_query
