import re


def filter_query(query: str) -> str:
    filtered_query = re.sub(r'\W+', ' ', query)
    return filtered_query
