from unittest.mock import patch

import pytest

from sweepai.agents.filter_agent import FilterAgent


class TestFilterAgentFilterQuery:
    def setUp(self):
        self.filter_agent = FilterAgent()

    @patch.object(
        FilterAgent,
        "chat",
        return_value="<filtered_query>\nfiltered query\n</filtered_query>",
    )
    def test_filter_query_regular_query(self, mock_chat):
        result = self.filter_agent.filter_query("regular query")
        assert result == "filtered query"

    @patch.object(
        FilterAgent,
        "chat",
        return_value="<filtered_query>\nfiltered edge case query\n</filtered_query>",
    )
    def test_filter_query_edge_case(self, mock_chat):
        result = self.filter_agent.filter_query("edge case query")
        assert result == "filtered edge case query"

    @patch.object(
        FilterAgent,
        "chat",
        return_value="<no_match>\nno match\n</no_match>",
    )
    def test_filter_query_no_match(self, mock_chat):
        result = self.filter_agent.filter_query("no match query")
        assert result == "no match query"

    @patch.object(
        FilterAgent,
        "chat",
        side_effect=Exception("ChatGPT service error"),
    )
    def test_filter_query_exception(self, mock_chat):
        result = self.filter_agent.filter_query("exception query")
        assert result == "exception query"
