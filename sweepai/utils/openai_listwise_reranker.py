# This should take a list of snippets and rerank them

reranking_prompt = """You are an expert at ranking the code snippets for the user query. You have to order the list of code snippets from the most relevant to the least relevant. 

Follow this example:
<code_snippets>
add.rs::0
```
// FILEPATH: add.rs:0-2
fn add(a: i32, b: i32) -> i32 {{
    a + b
}}
```

subtract.rs::0
```
// FILEPATH: subtract.rs:0-2
fn subtract(a: i32, b: i32) -> i32 {{
    a - b
}}
```
</code_snippets>

And if you thought the code snippet add.rs::0 is more relevant than subtract.rs::0 then you would rank it as:
<ranking>
add.rs::0
subtract.rs::0
</ranking>

The user query might contain a selection of line ranges in the following format:
[#file:foo.rs:4-10](values:file:foo.rs:4-10) this means the line range from 4 to 10 is selected by the user in the file foo.rs

This is the user's query: {user_query}
<code_snippets>
{code_snippets}
</code_snippets>

As a reminder the user query is:
<user_query>
{user_query}
</user_query>

The final reranking ordered from the most relevant to the least relevant is:
<ranking>"""

