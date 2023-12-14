from openai import ChatGPT

from sweepai.utils.utils import re

from .name_agent import serialize_method_name


class FilterBot(ChatGPT):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompt = """\
        <search_query>
        {search_query}
        </search_query>
        Filter out unnecessary terms from the above search query and return a refined query.
        <filtered_query>
        refined_query
        </filtered_query>
        ..."""

    def filter_query(self, search_query):
        filter_response = self.chat(
            content=self.prompt.format(search_query=search_query),
        )
        filter_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_matches = list(re.finditer(filter_pattern, filter_response, re.DOTALL))
        filter_matches = [match.group(1) for match in filter_matches]
        filtered_query = [
            serialize_method_name(filter_match.strip().strip('"').strip("'").strip("`"))
            for filter_match in filter_matches
        ]
        return filtered_query
