import re

from sweepai.core.chat import ChatGPT

prompt = """\
<search_query>
{search_query}
</search_query>
Filter out unnecessary terms from the above search query and return a cleaned query.
<cleaned_query>
cleaned_query
</cleaned_query>
"""

class QueryFilterAgent(ChatGPT):
    def filter_query(self, search_query):
        response = self.chat(content=prompt.format(search_query=search_query))
        cleaned_query_pattern = r"<cleaned_query>\n(.*?)\n</cleaned_query>"
        cleaned_query_match = re.search(cleaned_query_pattern, response, re.DOTALL)
        cleaned_query = cleaned_query_match.group(1).strip() if cleaned_query_match else ""
        return cleaned_query
