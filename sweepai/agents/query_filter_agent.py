import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """\
<search_query>
{search_query}
</search_query>
Filter out any unnecessary terms from the search query that do not aid in code search, while preserving the core terms required for an effective search.
"""

def serialize_query(query):
    return query.strip().strip('"')

def deserialize_query(query):
    return query.strip().strip('"')

class QueryFilterBot(ChatGPT):
    def filter_query(self, search_query):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        filter_response = self.chat(
            content=prompt.format(
                search_query=search_query,
            ),
        )
        filter_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_matches = list(re.finditer(filter_pattern, filter_response, re.DOTALL))
        filter_matches = [match.group(1) for match in filter_matches]
        filtered_query = [
            serialize_query(filter_match.strip().strip('"').strip("'").strip("`"))
            for filter_match in filter_matches
        ]
        return filtered_query
