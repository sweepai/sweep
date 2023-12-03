import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """\
<original_query>
{original_query}
</original_query>
Filter out unnecessary terms from the above search query and generate a new search query that is optimized for a lexical search.
<filtered_query>
filtered_query
</filtered_query>
"""

class FilterAgent(ChatGPT):
    def filter_search_query(
        self,
        original_query,
        chat_logger=None,
    ):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (chat_logger and chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        filter_response = self.chat(
            content=prompt.format(
                original_query=original_query,
            ),
        )
        filter_pattern = r"<filtered_query>\\n(.*?)\\n</filtered_query>"
        filter_match = re.search(filter_pattern, filter_response, re.DOTALL)
        filtered_query = filter_match.group(1).strip().strip('"').strip("'").strip("`")
        return filtered_query
