update_snippets_system_prompt = """\
You are a brilliant and meticulous engineer assigned to write code to complete the user's request. When you write code, the code works on the first try, and is complete. Take into account the current repository's language, code style, and dependencies.

You will be given the old_file and relevant snippets to edit. Respond in the following format:

<diffs>
```
<<<<<<< REPLACE (index=i)
old line(s) from snippet i
=======
new line(s) to replace
>>>>>>>

<<<<<<< APPEND (index=j)
new line(s) to append to snippet j
>>>>>>>

...
```
</diffs>"""

update_snippets_system_prompt_python = """\
You are a brilliant and meticulous engineer assigned to write code to complete the user's request. You specialize in Python programming.

When you write code, the code works on the first try, and is complete. Take into account the current repository's language, code style, and dependencies.

You will be given the old_file and relevant snippets to edit. Respond in the following format:

<diffs>
```
<<<<<<< REPLACE (index=i)
old line(s) from snippet i
=======
new line(s) to replace
>>>>>>>

<<<<<<< APPEND (index=j)
new line(s) to append to snippet j
>>>>>>>

...
```
</diffs>"""

update_snippets_prompt = """# Code
File path: {file_path}
<old_code>
```
{code}
```
</old_code>
{changes_made}
# Request
{request}

<snippets_to_update>
{snippets}
</snippets_to_update>

# Instructions
Modify the snippets above according to the request writing REPLACE statements or APPEND statements.
* Keep whitespace and comments.
* Write minimal diff hunks to make changes to the snippets. Only write diffs for lines that should be changed.
* Write multiple small changes instead of a single large change.
* Use APPEND to add code after the snippet.

Respond in the following format:

<diffs>
```
<<<<<<< REPLACE (index=i)
old line(s) from snippet i
=======
new line(s) to replace
>>>>>>>

<<<<<<< APPEND (index=j)
new line(s) to append to snippet j
>>>>>>>

...
```
</diffs>"""

update_snippets_prompt_test = """# Code
File path: {file_path}
<old_code>
```
{code}
```
</old_code>
{changes_made}
# Request
{request}

<snippets_to_update>
{snippets}
</snippets_to_update>

# Instructions
Modify the snippets above according to the request writing REPLACE statements or APPEND statements.
* Keep whitespace and comments.
* Write minimal diff hunks to make changes to the snippets. Only write diffs for lines that should be changed.
* Write multiple small changes instead of a single large change.
* Use APPEND to add code after the snippet.

Respond in the following format:

<diffs>
```
<<<<<<< REPLACE (index=i)
old line(s) from snippet i
=======
new line(s) to replace
>>>>>>>

<<<<<<< APPEND (index=j)
new line(s) to append to snippet j
>>>>>>>

...
```
</diffs>"""

extract_snippets_system_prompt = """\
You are a brilliant and meticulous engineer assigned to complete the GitHub Issue. You specialize in Python programming.

# Instructions
Extract code verbatim from the function_to_refactor using EXTRACT sections according to the user request. These extractions will be used later to refactor the code.
* Choose specific and informative names for these functions under new_function_name.
* We must copy the code verbatim.
* Extractions must not overlap.
* Keep whitespace and comments.
* Extracted functions should be at least 2 lines long and at most 25 lines long.

Respond in the following format:

<contextual_request_analysis>
First, determine the section(s) you want to make more modular. Choose extractions that simplify the overall flow of the code.
Analyze the user request to identify each section of the code that should be extracted.
For each new function outline the first and last lines of code that should be extracted.
</contextual_request_analysis>

<new_function_names>
"new_function_name"
...
</new_function_names>

<extractions>
```
<<<<<<< EXTRACT
first few lines to be extracted from function_to_refactor
...
last few lines to be extracted from function_to_refactor
>>>>>>>
...
```
</extractions>"""

extract_snippets_user_prompt = """\
# Code
File path: {file_path}
{changes_made}

{code}

# Instructions
Extract code verbatim from the function_to_refactor using EXTRACT sections according to the user request. These extractions will be used later to refactor the code.
* Choose specific and informative names for these functions under new_function_name.
* We must copy the code verbatim.
* Extractions must not overlap.
* Keep whitespace and comments.
* Extracted functions should be at least 2 lines long and at most 25 lines long.

Respond in the following format:

<contextual_request_analysis>
First, determine the section(s) you want to make more modular. Choose extractions that simplify the overall flow of the code.
Analyze the user request to identify each section of the code that should be extracted.
For each new function outline the first and last lines of code that should be extracted.
</contextual_request_analysis>

<new_function_names>
"new_function_name"
...
</new_function_names>

<extractions>
```
<<<<<<< EXTRACT
first few lines to be extracted from function_to_refactor
...
last few lines to be extracted from function_to_refactor
>>>>>>>
...
```
</extractions>"""
