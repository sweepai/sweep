import re


class QueryFilterAgent:
    def __init__(self):
        pass

    def filter_search_query(self, search_query: str) -> str:
        # Remove non-alphanumeric characters
        filtered_query = re.sub(r'\W+', ' ', search_query)
        # Remove extra spaces
        filtered_query = re.sub(r'\s+', ' ', filtered_query).strip()
        return filtered_query
