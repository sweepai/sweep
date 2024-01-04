import re

from sweepai.config.server import DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """\
<search_query>
{search_query}
</search_query>
Filter out unnecessary terms from the above search query and return a filtered search query.
<filtered_query>
filtered_query
</filtered_query>
..."""

class FilterBot(ChatGPT):
    def filter_query(self, search_query):
        self.model = DEFAULT_GPT35_MODEL
        filter_response = self.chat(
            content=prompt.format(search_query=search_query),
        )
        filter_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_matches = list(re.finditer(filter_pattern, filter_response, re.DOTALL))
        filtered_query = filter_matches[0].group(1).strip() if filter_matches else search_query
        return filtered_query
