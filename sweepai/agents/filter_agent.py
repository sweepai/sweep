from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.utils.utils import re

prompt = """\
<search_query>
{search_query}
</search_query>
Filter out unnecessary terms from the search query above and generate a new search query that only includes relevant terms.
<filtered_query>
filtered_query
</filtered_query>
..."""

class FilterAgent(ChatGPT):
    def filter_query_terms(self, search_query):
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
        filter_matches = [match.group(1) for match in filter_matches]
        filtered_query = filter_matches[0].strip().strip('"').strip("'").strip("`")
        return filtered_query
