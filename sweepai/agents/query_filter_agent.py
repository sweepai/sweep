import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT


def serialize_query(query):
    return query.strip().strip('"')

class QueryFilterBot(ChatGPT):
    def filter_query(self, query):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        prompt = f"<query>\n{query}\n</query>\nFilter out unnecessary terms from the above query."
        response = self.chat(content=prompt)
        query_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        query_match = re.search(query_pattern, response, re.DOTALL)
        cleaned_query = serialize_query(query_match.group(1).strip().strip('"').strip("'").strip("`"))
        return cleaned_query
