import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """\
<query>
{query}
</query>
Filter out any irrelevant or unnecessary terms from the above query for a lexical code search.
<filtered_query>
filtered_query
</filtered_query>
"""

class FilterAgent(ChatGPT):
    def filter_query(self, query):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        try:
            response = self.chat(content=prompt.format(query=query))
            filtered_query_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
            match = re.search(filtered_query_pattern, response, re.DOTALL)
            if match:
                return match.group(1).strip()
            else:
                raise ValueError("Filtered query not found in response.")
        except Exception as e:
            print(f"An error occurred while filtering the query: {e}")
            return query
