import pytest

from sweepai.agents.query_filter_agent import QueryFilterAgent


class TestQueryFilterAgent:
    def test_remove_common_stopwords(self):
        agent = QueryFilterAgent()
        query = "the a an in on for of with"
        expected = ""
        actual = agent.filter_query(query)
        assert actual == expected

    def test_remove_non_relevant_technical_terms(self):
        agent = QueryFilterAgent()
        query = "foo bar baz qux quux corge grault garply waldo fred plugh xyzzy thud"
        expected = "foo bar baz qux quux corge grault garply waldo fred plugh xyzzy thud"
        actual = agent.filter_query(query)
        assert actual == expected

    def test_retain_essential_keywords(self):
        agent = QueryFilterAgent()
        query = "python java javascript c c++ c# go rust swift kotlin"
        expected = "python java javascript c c++ c# go rust swift kotlin"
        actual = agent.filter_query(query)
        assert actual == expected
