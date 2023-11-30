import re

from sweepai.core.chat import ChatGPT


class KeyTermAgent(ChatGPT):
    def pre_filter_query(self, query: str) -> str:
        key_term_pattern = r"\[(.*?)\]"
        pre_filtered_query = re.sub(key_term_pattern, "", query)
        return pre_filtered_query
