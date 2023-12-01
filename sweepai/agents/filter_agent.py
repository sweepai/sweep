from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT


class FilterBot(ChatGPT):
    def filter_query_terms(self, query, is_paying_user):
        self.model = DEFAULT_GPT4_32K_MODEL if is_paying_user else DEFAULT_GPT35_MODEL
        prompt = f"Given the search query '{query}', filter out unnecessary terms."
        filtered_query = self.chat(content=prompt)
        return filtered_query
