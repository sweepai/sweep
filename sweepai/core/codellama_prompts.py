recreate_file_user_prompt = """
[INST]
I have the following file `{filename}` that I would like to modify to complete the task.

```
{code}
```

Task:
{task}

Respond in the following format:

Step-by-step thoughts: (max 5 thoughts)
1. Thought 1
2. Thought 2

[CODE]
```
the code
```
[CODE]

Now complete the task.
[/INST]

[SOLUTION]
"""
