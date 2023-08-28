recreate_file_prompt = """
[INST]
I have the following file `{filename}` that I would like to modify to complete the task.

```
{code}
```

Task:
{task}

Response format:

Step-by-step thoughts: (max 5 thoughts)
1. Thought 1
2. Thought 2

Commit message: "the commit message"

```
the code
```

Now complete the task.
[/INST]

[SOLUTION]
"""
