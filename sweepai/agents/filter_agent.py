import re


def filter_query_terms(query: str) -> str:
    """
    This function accepts a query string and returns a filtered query string.
    It uses regular expressions to identify and remove unnecessary terms from the query.

    Args:
        query (str): The query string to be filtered.

    Returns:
        str: The filtered query string.
    """
    unnecessary_terms = ['the', 'a', 'an', 'in', 'on', 'at', 'and', 'or', 'is', 'are', 'was', 'were']
    for term in unnecessary_terms:
        query = re.sub(f'\\b{term}\\b', '', query)
    return query.strip()
