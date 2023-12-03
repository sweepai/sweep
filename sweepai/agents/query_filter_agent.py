import re

from sweepai.core.chat import ChatGPT


class QueryFilterAgent(ChatGPT):
    """
    An agent that filters unnecessary terms out of a search query.

    Inherits from the ChatGPT class.
    """

    def filter_query(self, query: str) -> str:
        """
        Filters unnecessary terms from the search query.

        Args:
            query (str): The search query to be filtered.

        Returns:
            str: The filtered search query.
        """
        unnecessary_terms_pattern = r"<pattern_to_match_unnecessary_terms>"
        filtered_query = re.sub(unnecessary_terms_pattern, "", query)
        return filtered_query
