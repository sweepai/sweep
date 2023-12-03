import re

from sweepai.core.chat import ChatGPT

prompt = """
<original_query>
{query}
</original_query>
Filter out unnecessary terms from the above search query.
"""

class FilterAgent(ChatGPT):
    def filter_query(self, query):
        response = self.chat(content=prompt.format(query=query))
        filtered_query = re.search(r"<filtered_query>\n(.*?)\n</filtered_query>", response, re.DOTALL).group(1)
        return filtered_query.strip()
```

```python
# sweepai/agents/filter_agent_test.py
import pytest

from sweepai.agents.filter_agent import FilterAgent


def test_filter_query():
    agent = FilterAgent()

    # Test with a simple query
    query = "Find all instances of the variable x in the code"
    filtered_query = agent.filter_query(query)
    assert filtered_query == "variable x"

    # Test with a complex query
    query = "Find all instances of the variable x in the code, but ignore comments and docstrings"
    filtered_query = agent.filter_query(query)
    assert filtered_query == "variable x ignore comments docstrings"

    # Test with a query that doesn't need filtering
    query = "variable x"
    filtered_query = agent.filter_query(query)
    assert filtered_query == "variable x"
