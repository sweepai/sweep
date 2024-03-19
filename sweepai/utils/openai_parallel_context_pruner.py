"""This should take a list of snippets and filter them"""
import re
import threading

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Snippet


filtering_prompt = """You are a powerful code search engine. Determine if the following code snippet is relevant at all to the user's query.
This is the user's query: 
<user_query>
{user_query}
</user_query>

This is the code snippet:
<code_snippet>
{code_snippet}
</code_snippet>

<contextual_request_analysis>
* Read the entire contents of the snippet and determine whether it might be necessary for the user's query.
...
</contextual_request_analysis>

Return a score from 1 to 10 below:
<score>
1 means completely irrelevant, 5 means it might be relevant, 10 means absolutely necessary
</score>
"""

SNIPPET_THRESHOLD = 3

class FilterSnippetBot(ChatGPT):
    def is_snippet_relevant(
        self,
        user_query,
        code_snippet,
    ):
        self.model = DEFAULT_GPT4_32K_MODEL
        self.messages = []
        # if the regex match fails return the original list
        # gpt doesn't add all snippets, we move all of the dropped snippets to the end in the original order
        # if we add duplicate snippets, we remove the duplicates
        score_pattern = r"<score>\n(.*?)\n</score>"
        formatted_code_snippet = self.format_code_snippet(code_snippet)
        score_response = self.chat(
            content=filtering_prompt.format(
                user_query=user_query,
                code_snippet=formatted_code_snippet,
            ),
        )
        score_matches = re.search(score_pattern, score_response, re.DOTALL)
        if score_matches is None:
            return False
        snippet_score = score_matches.group(1)
        snippet_score = snippet_score.strip()
        snippet_score = int(snippet_score) if snippet_score.isdigit() else 10
        return snippet_score > SNIPPET_THRESHOLD
    
    def format_code_snippet(self, code_snippet: Snippet):
        snippet_str = \
f"""{code_snippet.denotation}
```
{code_snippet.get_snippet(False, False)}
```
"""
        return snippet_str
        
def parallel_prune_snippets(user_query, code_snippets):
    filtered_snippets = [None] * len(code_snippets)
    
    def filter_snippet(index, snippet):
        bot = FilterSnippetBot()
        score = bot.is_snippet_relevant(user_query, snippet)
        if score:
            filtered_snippets[index] = snippet
    
    threads = [threading.Thread(target=filter_snippet, args=(index, snippet)) 
               for index, snippet in enumerate(code_snippets)]
    
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    
    return [snippet for snippet in filtered_snippets if snippet is not None]
    
if __name__ == "__main__":
    # generate some test snippets
    def generate_snippet_obj(idx, title="add.py", contents = "def add(a: int, b: int) -> int:\n    return a + b"):
        snippet = Snippet(file_path=title, content=("\n" * (idx - 1) + contents), start=idx, end=idx + 1)
        return snippet
    code_snippets = [
        generate_snippet_obj(idx) for idx in range(15)
    ] + [
        generate_snippet_obj(idx, title="subtract.py", contents="def subtract(a: int, b: int) -> int:\n    return a - b") for idx in range(15)
    ]
    try:
        # rank them
        filtered_snippets = parallel_prune_snippets("I want to add two numbers.", code_snippets)
        print("\n".join([s.denotation for s in filtered_snippets]))
        print("Number of snippets remaining:", len(filtered_snippets))
        # assert monotonic indices and that all subtracts are filtered
        assert all(filtered_snippets[i].denotation == "add.py" for i in range(15))
    except Exception as e:
        import pdb
        pdb.post_mortem()
        raise e