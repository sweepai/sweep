import re

from sweepai.core.chat import ChatGPT

prompt = """\
<search_query>
{search_query}
</search_query>
Filter out unnecessary terms from the above search query and return the filtered query in the below format:
<filtered_query>
filtered_query
</filtered_query>
"""

class QueryFilterAgent(ChatGPT):
    def filter_query(self, search_query):
        response = self.chat(content=prompt.format(search_query=search_query))
        filtered_query_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filtered_query_match = re.search(filtered_query_pattern, response, re.DOTALL)
        filtered_query = filtered_query_match.group(1).strip() if filtered_query_match else ""
        return filtered_query
