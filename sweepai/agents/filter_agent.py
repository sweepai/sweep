from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.utils.utils import re

prompt = """\
<old_query>
{old_query}
</old_query>
Filter the above query by removing unnecessary terms. The filtered query should be more effective for a lexical search.
<filtered_query>
filtered_query
</filtered_query>
..."""

def serialize_filtered_query(filtered_query):
    return filtered_query.strip().strip('"')

class FilterAgent(ChatGPT):
    def filter_query(
        self,
        old_query,
        count=1,
    ):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        filter_response = self.chat(
            content=prompt.format(
                old_query=old_query,
                count=count,
            ),
        )
        filter_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_matches = list(re.finditer(filter_pattern, filter_response, re.DOTALL))
        filter_matches = [match.group(1) for match in filter_matches]
        filtered_queries = [
            serialize_filtered_query(filter_match.strip().strip('"').strip("'").strip("`"))
            for filter_match in filter_matches
        ]
        return filtered_queries
