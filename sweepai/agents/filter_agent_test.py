import pytest

from sweepai.agents.filter_agent import filter_query_terms


def test_filter_query_terms_no_unnecessary_terms():
    """
    Test the filter_query_terms function with a query that does not contain any unnecessary terms.
    """
    query = "python code"
    expected = "python code"
    assert filter_query_terms(query) == expected

def test_filter_query_terms_one_unnecessary_term():
    """
    Test the filter_query_terms function with a query that contains one unnecessary term.
    """
    query = "the python code"
    expected = "python code"
    assert filter_query_terms(query) == expected

def test_filter_query_terms_multiple_unnecessary_terms():
    """
    Test the filter_query_terms function with a query that contains multiple unnecessary terms.
    """
    query = "the python code in the repository"
    expected = "python code repository"
    assert filter_query_terms(query) == expected

def test_filter_query_terms_unnecessary_terms_different_positions():
    """
    Test the filter_query_terms function with a query that contains unnecessary terms in different positions.
    """
    query = "the python and java or c++"
    expected = "python java c++"
    assert filter_query_terms(query) == expected

def test_filter_query_terms_unnecessary_terms_and_punctuation():
    """
    Test the filter_query_terms function with a query that contains unnecessary terms and punctuation.
    """
    query = "the python, java, and c++"
    expected = "python, java, c++"
    assert filter_query_terms(query) == expected

def test_filter_query_terms_empty_query():
    """
    Test the filter_query_terms function with an empty query.
    """
    query = ""
    expected = ""
    assert filter_query_terms(query) == expected

def test_filter_query_terms_only_unnecessary_terms():
    """
    Test the filter_query_terms function with a query that contains only unnecessary terms.
    """
    query = "the a an in on at and or is are was were"
    expected = ""
    assert filter_query_terms(query) == expected
