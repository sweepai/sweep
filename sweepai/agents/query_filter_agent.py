import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT


class QueryFilterBot(ChatGPT):
    prompt = """\
    <query>
    {query}
    </query>
    Filter out unnecessary terms from the above query and generate a new query.

    <filtered_query>
    filtered_query
    </filtered_query>
    ..."""

    def filter_query(self, query, count=1):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        query_response = self.chat(
            content=self.prompt.format(query=query, count=count),
        )
        query_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        query_matches = list(re.finditer(query_pattern, query_response, re.DOTALL))
        query_matches = [match.group(1) for match in query_matches]
        filtered_queries = [
            self.serialize_query(query_match.strip().strip('"').strip("'").strip("`"))
            for query_match in query_matches
        ]
        return filtered_queries

    @staticmethod
    def serialize_query(query):
        return query.strip().strip('"')
