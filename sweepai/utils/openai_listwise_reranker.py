"""This should take a list of snippets and rerank them"""
import re

from loguru import logger

from sweepai.config.server import DEFAULT_GPT4_32K_MODEL
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import Snippet
from sweepai.logn.cache import file_cache

# use this later
# # Contextual Request Analysis:
# <contextual_request_analysis>
# * Read each code snippet and assign each a relevance score.
# ...
# </contextual_request_analysis>

# this is roughly 66% of it's optimal performance - it's worth optimizing more in the future

reranking_system_prompt = """You are a powerful code search engine. You must order the list of code snippets from most relevant to least relevant for resolving the user's query, which is part of a GitHub issue.

The most relevant code snippets are the ones we need to edit to resolve the user's issue. The next most relevant snippets are the ones that are crucial to read to make valid code changes to correctly resolve the user's issue.

Respond in the following format:
<analysis>
Analyze the user's request to determine which modules must be edited to resolve the GitHub Issue. Then determine all modules that must be read or used to resolve the user's request, such as crucial helper functions or backend services.
</analysis>
<ranking>
most_relevant_file_path:start_line-end_line
second_most_relevant_file_path:start_line-end_line
...
least_relevant_file_path:start_line_end_line
</ranking>

Here is an example:
<example>
<example_input>
<user_query>
Correct the Flask app's add endpoint to use add instead of multiply.
</user_query>
<code_snippets>
<code_snippet>
<code_snippet_source>
utils/add.py:0-1
</code_snippet_source>
<code_snippet_content>
```
def add(a: int, b: int) -> int:
    return a + b
```
</code_snippet_content>
</code_snippet>

<code_snippet>
<code_snippet_source>
utils/subtract.py:0-1
</code_snippet_source>
<code_snippet_content>
```
def subtract(a: int, b: int) -> int:
    return a - b
```
</code_snippet_content>
</code_snippet>
</code_snippets>
<code_snippet>
<code_snippet_source>
app.py:0-12
</code_snippet_source>
<code_snippet_content>
```
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/add', methods=['GET'])
def add():
    a = float(request.args.get('a', 0))
    b = float(request.args.get('b', 0))
    result = a * b
    return jsonify({{'result': result}})

if __name__ == '__main__':
    app.run(debug=True)
```
</code_snippet_content>
</code_snippet>
</code_snippets>
</example_input>

<example_output>
<analysis>
We need to make the change in the Flask app, which is in app.py. We must use the helper function add, which is defined in utils/add.py, so it must also be relevant.
</analysis>

<ranking>
app.py:0-12
utils/add.py:0-1
utils/subtract.py:0-1
</ranking>
</example_output>
</example>"""

reranking_user_prompt = """
This is the user's query: 

<user_query>
{user_query}
</user_query>

Here is a list of code snippets:

<code_snippets>
{formatted_code_snippets}
</code_snippets>

Remember: The most relevant files are the ones we need to edit to resolve the user's issue. The next most relevant snippets are the ones that are crucial to read while editing the other code files to correctly resolve the user's issue.

As a reminder the user query is:
<user_query>
{user_query}
</user_query>

And the response format is:
<analysis>
Analyze the user's request to determine which modules must be edited to resolve the GitHub Issue. Then determine all modules that must be read or used to resolve the user's request, such as crucial helper functions or backend services.
</analysis>

<ranking>
most_relevant_file_path:start_line-end_line
second_most_relevant_file_path:start_line-end_line
...
least_relevant_file_path:start_line_end_line
</ranking>

Return the correct ranking of the code snippets below:"""


class RerankSnippetsBot(ChatGPT):
    def rerank_list_for_query(
        self,
        user_query,
        code_snippets,
    ):
        self.model = DEFAULT_GPT4_32K_MODEL
        self.messages = [Message(
            role="system",
            content=reranking_system_prompt
        )]
        # if the regex match fails return the original list
        # gpt doesn't add all snippets, we move all of the dropped snippets to the end in the original order
        # if we add duplicate snippets, we remove the duplicates
        ranking_pattern = r"<ranking>\n(.*?)\n</ranking>"
        formatted_code_snippets = self.format_code_snippets(code_snippets)
        try:
            ranking_response = self.chat_anthropic(
                content=reranking_user_prompt.format(
                    user_query=user_query,
                    formatted_code_snippets=formatted_code_snippets,
                ),
            )
        except Exception as e:
            logger.error(e)
            ranking_response = self.chat(
                content=reranking_user_prompt.format(
                    user_query=user_query,
                    formatted_code_snippets=formatted_code_snippets,
                ),
            )
        ranking_matches = re.search(ranking_pattern, ranking_response, re.DOTALL)
        if ranking_matches is None:
            return code_snippets
        snippet_ranking = ranking_matches.group(1)
        snippet_ranking = snippet_ranking.strip()
        snippet_ranking = snippet_ranking.split("\n")
        # assert all snippet denotations are within our original list
        original_denotations = [snippet.denotation for snippet in code_snippets]
        snippet_ranking = [snippet for snippet in snippet_ranking if snippet in original_denotations]
        # dedup the list with stable ordering
        snippet_ranking = list(dict.fromkeys(snippet_ranking))
        if len(snippet_ranking) < len(code_snippets):
            # add the remaining snippets in the original order
            remaining_snippets = [snippet.denotation for snippet in code_snippets if snippet.denotation not in snippet_ranking]
            snippet_ranking.extend(remaining_snippets)
        # sort the snippets using the snippet_ranking
        ranked_snippets = sorted(code_snippets, key=lambda snippet: snippet_ranking.index(snippet.denotation))
        return ranked_snippets
    
    def format_code_snippets(self, code_snippets: list[Snippet]):
        result_str = ""
        for snippet in code_snippets:
            snippet_str = \
f"""<code_snippet>
<code_snippet_source>
{snippet.denotation}
</code_snippet_source>
<code_snippet_content>
```
{snippet.get_snippet(False, False)}
```
</code_snippet_content>
"""
            result_str += snippet_str + "\n"
        result_removed_trailing_newlines = result_str.rstrip("\n")
        return result_removed_trailing_newlines

@file_cache()
def listwise_rerank_snippets(
    user_query,
    code_snippets,
):
    # iterate from the bottom of the list to the top, sorting each n items then resorting with next n // 2 items
    number_to_rerank_at_once = 10
    stride = number_to_rerank_at_once // 2
    final_ordering = []
    prev_chunk = []
    for idx in range(len(code_snippets) - stride, 0, -stride):
        # if there is no prev_chunk, rerank the bottom n items
        if not prev_chunk:
            reranked_chunk = RerankSnippetsBot().rerank_list_for_query(user_query, code_snippets[idx - stride:idx + stride])
        # if there's a prev_chunk, rerank this chunk with the prev_chunk
        else:
            # chunk_to_rerank should be 5 new items and the top 5 items of the prev_chunk
            chunk_to_rerank = code_snippets[idx - stride:idx] + prev_chunk[:stride]
            reranked_chunk = RerankSnippetsBot().rerank_list_for_query(user_query, chunk_to_rerank)
        # last iteration, add all items
        if idx - stride <= 0:
            final_ordering = reranked_chunk + final_ordering
        else:
            # add the last n // 2 items to the final_ordering
            final_ordering = reranked_chunk[-stride:] + final_ordering
        prev_chunk = reranked_chunk
    return final_ordering
    
if __name__ == "__main__":
    # generate some test snippets
    def generate_snippet_obj(idx):
        snippet = Snippet(file_path="add.py", content=("\n" * (idx - 1) + "def add(a: int, b: int) -> int:\n    return a + b"), start=idx, end=idx + 1)
        return snippet
    code_snippets = [
        generate_snippet_obj(idx) for idx in range(30)
    ]
    try:
        # rank them
        final_ordering = listwise_rerank_snippets("I want to add two numbers.", code_snippets)
        print("\n".join([s.denotation for s in final_ordering]))
        # assert no duplicates or missing snippets
        assert len(set(final_ordering)) == len(final_ordering)
    except Exception as e:
        import pdb
        pdb.post_mortem()
        raise e
