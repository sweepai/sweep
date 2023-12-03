import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """
<search_query>
{search_query}
</search_query>
Filter out unnecessary terms from the above search query and generate a clean query.
<filtered_query>
clean_query
</filtered_query>
"""

def serialize_query(query):
    return query.strip().strip('"').strip("'").strip("`")

class QueryFilterBot(ChatGPT):
    def filter_query(self, search_query, is_paying_user=False):
        self.model = DEFAULT_GPT4_32K_MODEL if is_paying_user else DEFAULT_GPT35_MODEL
        response = self.chat(content=prompt.format(search_query=search_query))
        query_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        query_match = re.search(query_pattern, response, re.DOTALL)
        if query_match:
            return serialize_query(query_match.group(1))
        else:
            return None
