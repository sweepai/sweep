from unittest.mock import MagicMock, patch

import pytest

from sweepai.agents.query_filter_agent import QueryFilterBot


class TestQueryFilterBot:
    def setup(self):
        self.bot = QueryFilterBot()

    @patch.object(QueryFilterBot, 'chat', return_value="<filtered_query>\nfiltered query\n</filtered_query>")
    def test_filter_query(self, mock_chat):
        # Test case: no terms to filter
        query = "query with no terms to filter"
        expected_result = ["filtered query"]
        assert self.bot.filter_query(query) == expected_result

        # Test case: multiple terms to filter
        query = "query with multiple terms to filter"
        expected_result = ["filtered query"]
        assert self.bot.filter_query(query) == expected_result

        # Test case: all terms to filter
        query = "query with all terms to filter"
        expected_result = ["filtered query"]
        assert self.bot.filter_query(query) == expected_result

        # Test case: empty query
        query = ""
        expected_result = ["filtered query"]
        assert self.bot.filter_query(query) == expected_result
