from sweepai.agents.pr_description_bot import ChatGPT
from sweepai.config.server import DEFAULT_GPT35_MODEL
from sweepai.utils.utils import re


class QueryFilterAgent(ChatGPT):
    def __init__(self):
        super().__init__()
        self.model = DEFAULT_GPT35_MODEL

    def filter_search_query(self, search_query: str) -> str:
        prompt = """\
        Filter out unnecessary terms from the following search query to improve the relevance of search results:
        <search_query>
        {search_query}
        </search_query>

        Format your response using the following XML tags:
        <filtered_query>
        # Filtered Query
        The filtered search query with unnecessary terms removed.
        </filtered_query>"""

        filtered_query_pattern = r"<filtered_query>\n(.*?)\n</filtered_query>"
        filter_response = self.chat(
            content=prompt.format(
                search_query=search_query,
            ),
        )
        filtered_query_matches = re.search(filtered_query_pattern, filter_response, re.DOTALL)
        if filtered_query_matches is None:
            return search_query
        
        filtered_query = filtered_query_matches.group(1).strip()
        return filtered_query if filtered_query else search_query

# Unit tests for QueryFilterAgent
def test_filter_search_query():
    agent = QueryFilterAgent()

    # Mock the chat method to return a predefined response
    agent.chat = lambda content: "<filtered_query>\nfiltered content\n</filtered_query>"

    assert agent.filter_search_query("original content") == "filtered content"
    assert agent.filter_search_query("") == ""
    assert agent.filter_search_query(" ") == " "
    assert agent.filter_search_query("no unnecessary terms") == "no unnecessary terms"
    assert agent.filter_search_query("only unnecessary terms") == "only unnecessary terms"

    # Mock the chat method to simulate no response from the language model
    agent.chat = lambda content: ""
    assert agent.filter_search_query("original content") == "original content"
