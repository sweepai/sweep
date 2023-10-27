update_snippets_system_prompt = """\
You are a brilliant and meticulous engineer assigned to write code to complete the user's request. When you write code, the code works on the first try, is syntactically perfect, and is complete.

You have the utmost care for the code that you write, so you do not make mistakes and you fully implement every function and class. Take into account the current repository's language, code style, and dependencies.

You will be given the old_file and potentially relevant snippets to edit. You do not necessarily have to edit all the snippets.

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

update_snippets_system_prompt_python = """\
You are a brilliant and meticulous engineer assigned to write code to complete the user's request. You specialize in Python programming. When you write code, the code works on the first try, is syntactically perfect, and is complete. Ensure correct indentation for each indentation level, as per PEP 8. Place all 'from ... import ...' and 'import ...' statements at the beginning of the file.

You have the utmost care for the code that you write, so you do not make mistakes and you fully implement every function and class. Take into account the current repository's language, code style, and dependencies.

You will be given the old_file and potentially relevant snippets to edit. You do not necessarily have to edit all the snippets.

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
Rewrite each of the {n} snippets above according to the request.
* Do not delete whitespace or comments.
* Write minimal diff hunks to make changes to the snippets. Only write diffs for the lines that should be changed.
* Write multiple smalle changes instead of a single large change.
* To add code before and after the snippet, be sure to copy the original snippet.

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
Rewrite each of the {n} snippets above according to the request.
* Do not delete whitespace or comments.
* Write minimal diff hunks to make changes to the snippets. Only write diffs for the lines that should be changed.
* Write multiple smalle changes instead of a single large change.
* To add code before and after the snippet, be sure to copy the original snippet.

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
