import re

from sweepai.core.chat import ChatGPT

prompt = """\
<original_query>
{original_query}
</original_query>
Filter out unnecessary terms from the above search query and generate a refined query.

<refined_query>
refined_query
</refined_query>
"""

class QueryFilterAgent(ChatGPT):
    def __init__(self):
        super().__init__()

    def filter_query(self, original_query):
        response = self.chat(
            content=prompt.format(original_query=original_query),
        )
        refined_query_pattern = r"<refined_query>\n(.*?)\n</refined_query>"
        refined_query_matches = re.search(refined_query_pattern, response, re.DOTALL)
        if refined_query_matches is None:
            return original_query
        refined_query = refined_query_matches.group(1).strip().strip('"').strip("'").strip("`")
        return refined_query
