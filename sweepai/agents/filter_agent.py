from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT


class FilterAgent(ChatGPT):
    def filter_query(self, query, is_paying_user):
        self.model = DEFAULT_GPT4_32K_MODEL if is_paying_user else DEFAULT_GPT35_MODEL
        prompt = f"<query>\n{query}\n</query>\nFilter unnecessary terms from the query."
        response = self.chat(content=prompt)
        filtered_query = response.split("\n")[1]
        return filtered_query
