import pytest

from sweepai.agents.filter_agent import FilterAgent


class TestFilterAgent:
    def setup_method(self, method):
        self.filter_agent = FilterAgent()

    def test_filter_search_query(self):
        test_cases = [
            ("This is a test query", ["This", "is", "a", "test", "query"]),
            ("Filter out unnecessary terms", ["Filter", "out", "unnecessary", "terms"]),
            ("", []),
            ("Only one term", ["Only", "one", "term"]),
            ("Multiple   spaces", ["Multiple", "spaces"]),
            ("Special characters !@#$%^&*()", ["Special", "characters"]),
        ]

        for query, expected in test_cases:
            result = self.filter_agent.filter_search_query(query)
            assert result == expected, f"For query: {query}, expected: {expected}, but got: {result}"
