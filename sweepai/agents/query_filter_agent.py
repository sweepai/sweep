from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT


class QueryFilterBot(ChatGPT):
    def filter_query(self, query):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        prompt = "You must rewrite the user's github issue to leverage the docs. Using the github issue, write a search query that searches for the potential answer using the documentation. This query will be sent to a documentation search engine with vector and lexical based indexing. Make this query contain keywords relevant to the documentation."
        filtered_query = self.chat(content=prompt.format(query=query))
        return filtered_query
