# filter_agent.py
import re

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL, DEFAULT_GPT35_MODEL
from sweepai.core.chat import ChatGPT

prompt = """\
<old_query>
{old_query}
</old_query>
Filter out unnecessary terms from the above search query and generate a new query.
<new_query>
new_query
</new_query>
..."""

class FilterBot(ChatGPT):
    def filter_query(self, old_query):
        self.model = (
            DEFAULT_GPT4_32K_MODEL
            if (self.chat_logger and self.chat_logger.is_paying_user())
            else DEFAULT_GPT35_MODEL
        )
        filter_response = self.chat(
            content=prompt.format(old_query=old_query),
        )
        query_pattern = r"<new_query>\n(.*?)\n</new_query>"
        query_matches = list(re.finditer(query_pattern, filter_response, re.DOTALL))
        query_matches = [match.group(1) for match in query_matches]
        filtered_query = [
            self.serialize_filtered_query(query_match.strip().strip('"').strip("'").strip("`"))
            for query_match in query_matches
        ]
        return filtered_query

    @staticmethod
    def serialize_filtered_query(filtered_query):
        return filtered_query.strip().strip('"')

# filter_agent_test.py
import pytest

from sweepai.agents.filter_agent import FilterBot


def test_filter_query():
    bot = FilterBot()
    assert bot.filter_query("search for all python files") == ["search python files"]
    assert bot.filter_query("find all the bugs in the code") == ["find bugs code"]
    assert bot.filter_query("look for any syntax errors") == ["look syntax errors"]
    assert bot.filter_query("") == [""]
