from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """
<search_query>
{search_query}
</search_query>
Filter out unnecessary terms from the search query above and return a filtered query.
"""

class FilterBot(ChatGPT):
    def filter_query(self, search_query: str) -> str:
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        filtered_query = self.chat(
            content=prompt.format(search_query=search_query),
        )
        return filtered_query
