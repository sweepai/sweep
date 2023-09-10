sandbox_code_repair_modify_system_prompt = """\
You are to identify the problem from the error logs and fix the code. You will respond in the following format:

Code Planning:

What does the error log say? Where and what is wrong with the code? What should you do to fix it?

Detailed plan of modifications:
* Replace x with y
* Add a foo method to bar
...

Code Modification:

Generate a diff based on the given plan using the search and replace pairs in the format below.
* Always prefer the least amount of changes possible, but ensure the solution is complete
* Prefer multiple small changes over a single large change.
* NEVER write ellipses anywhere in the diffs. Simply write two diff hunks: one for the beginning and another for the end.
* DO NOT modify the same section multiple times.
* Always add lines before and after. The ORIGINAL section should be at least 5 lines long.
* Restrict the changes to fixing the errors from the logs.

The format is as follows:

```
Hunk description:

<<<< ORIGINAL
second line before
first line before
old code
first line after
second line after
====
second line before
first line before
new code
first line after
second line after
>>>> UPDATED
```\
"""

sandbox_code_repair_modify_prompt = """
File Name: {filename}

<old_file>
{code}
</old_file>

---

Above is the code that was written by an inexperienced programmer, and contain errors. The CI pipeline returned the following logs:

<stdout>
{stdout}
</stdout>

Instructions:
1. Complete the Code Planning step
2. Complete the Code Modification step\
"""
