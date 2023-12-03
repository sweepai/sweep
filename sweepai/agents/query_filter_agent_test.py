from unittest.mock import patch

import pytest

from sweepai.agents.query_filter_agent import QueryFilterBot, serialize_query


def test_serialize_query():
    assert serialize_query("  test_query  ") == "test_query"
    assert serialize_query('"test_query"') == "test_query"
    assert serialize_query("'test_query'") == "test_query"
    assert serialize_query("`test_query`") == "test_query"
    assert serialize_query(' "test_query" ') == "test_query"

@pytest.fixture
def query_bot():
    return QueryFilterBot()

@patch.object(QueryFilterBot, "chat")
def test_filter_query(mock_chat, query_bot):
    mock_chat.return_value = "<filtered_query>\nclean_query\n</filtered_query>"
    assert query_bot.filter_query("test query with unnecessary terms") == "clean_query"

    mock_chat.return_value = "<filtered_query>\nclean_query_without_stopwords\n</filtered_query>"
    assert query_bot.filter_query("test query with common stopwords") == "clean_query_without_stopwords"

    mock_chat.return_value = "<filtered_query>\nclean_query_without_noise\n</filtered_query>"
    assert query_bot.filter_query("test query with domain-related noise") == "clean_query_without_noise"

    mock_chat.return_value = "<filtered_query>\nclean_query_without_punctuation\n</filtered_query>"
    assert query_bot.filter_query("test query with punctuation!") == "clean_query_without_punctuation"
