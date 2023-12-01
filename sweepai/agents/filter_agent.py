import re

from sweepai.core.chat import ChatGPT

prompt = """\
<old_query>
{old_query}
</old_query>
Filter out unnecessary terms from the above search query. The filtered query should be clear and relevant for the lexical search.
<filtered_query>
filtered_query
</filtered_query>
..."""

def serialize_search_term(search_term):
    if "." in search_term:
        return search_term.split(". ")[-1].strip('"')
    return search_term.strip().strip('"')

class FilterAgent(ChatGPT):
    def filter_search_query(self, old_query):
        filter_response = self.chat(content=prompt.format(old_query=old_query))
        filter_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_matches = list(re.finditer(filter_pattern, filter_response, re.DOTALL))
        filter_matches = [match.group(1) for match in filter_matches]
        filtered_query = [
            serialize_search_term(filter_match.strip().strip('"').strip("'").strip("`"))
            for filter_match in filter_matches
        ]
        return filtered_query
