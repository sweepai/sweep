from unittest.mock import Mock

import pytest

from sweepai.agents import query_filter_agent


class TestQueryFilterBot:
    def setup_method(self):
        self.bot = query_filter_agent.QueryFilterBot()
        self.bot.chat = Mock()

    def test_filter_query_common_terms(self):
        self.bot.chat.return_value = "<filtered_query>\nrelevant terms\n</filtered_query>"
        result = self.bot.filter_query("common less relevant terms")
        assert result == "relevant terms"

    def test_filter_query_optimized(self):
        self.bot.chat.return_value = "<filtered_query>\noptimized query\n</filtered_query>"
        result = self.bot.filter_query("optimized query")
        assert result == "optimized query"

    def test_filter_query_empty(self):
        self.bot.chat.return_value = "<filtered_query>\n\n</filtered_query>"
        result = self.bot.filter_query("")
        assert result == ""

    def test_filter_query_only_unnecessary_terms(self):
        self.bot.chat.return_value = "<filtered_query>\n\n</filtered_query>"
        result = self.bot.filter_query("unnecessary terms")
        assert result == ""

    def test_filter_query_special_characters(self):
        self.bot.chat.return_value = "<filtered_query>\nrelevant terms\n</filtered_query>"
        result = self.bot.filter_query("unnecessary terms !@#$%^&*()")
        assert result == "relevant terms"
