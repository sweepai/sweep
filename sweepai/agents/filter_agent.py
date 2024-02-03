import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT


class FilterAgent(ChatGPT):
    def filter_search_query(self, search_query):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        prompt = f"Given the search query:\n{search_query}\nFilter out unnecessary terms and return a refined search query."
        filter_response = self.chat(content=prompt)
        filter_pattern = r"Refined search query:\n(.*?)\n"
        filter_match = re.search(filter_pattern, filter_response, re.DOTALL)
        filtered_query = filter_match.group(1).strip()
        return filtered_query
