import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """\
<search_query>
{search_query}
</search_query>
Pre-filter key terms from the search query above. Optimize for relevance and clarity.

<filtered_query>
filtered_query
</filtered_query>
..."""

class QueryFilterAgent(ChatGPT):
    def filter_query(self, search_query):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        filter_response = self.chat(
            content=prompt.format(search_query=search_query),
        )
        filter_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_matches = list(re.finditer(filter_pattern, filter_response, re.DOTALL))
        filtered_query = [match.group(1) for match in filter_matches]
        return filtered_query[0] if filtered_query else search_query
