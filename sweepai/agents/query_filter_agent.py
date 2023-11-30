import re

from sweepai.core.chat import ChatGPT

prompt = """\
<original_query>
{query}
</original_query>
Filter out unnecessary terms from the above query. The filtered query should only contain relevant terms that will aid in a lexical search.
<filtered_query>
filtered_query
</filtered_query>
"""

def serialize_query(query):
    return query.strip().strip('"')

class QueryFilterAgent(ChatGPT):
    def filter_query(self, query):
        response = self.chat(content=prompt.format(query=query))
        query_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        query_match = re.search(query_pattern, response, re.DOTALL)
        filtered_query = serialize_query(query_match.group(1).strip().strip('"').strip("'").strip("`"))
        return filtered_query
