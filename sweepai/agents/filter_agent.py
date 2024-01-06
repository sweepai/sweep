import re

from sweepai.core.chat import ChatGPT

prompt = """\
<old_query>
{old_query}
</old_query>
Filter out unnecessary terms from the above query. Optimize for relevance and clarity.

<filtered_query>
filtered_query
</filtered_query>
..."""

class FilterAgent(ChatGPT):
    def filter_query(self, old_query):
        filter_response = self.chat(
            content=prompt.format(old_query=old_query),
        )
        filter_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_matches = list(re.finditer(filter_pattern, filter_response, re.DOTALL))
        filter_matches = [match.group(1) for match in filter_matches]
        filtered_query = ' '.join(filter_matches)
        return filtered_query
