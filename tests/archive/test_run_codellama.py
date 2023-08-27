import modal

# app_name = "example-tgi-Phind-CodeLlama-34B-v1"
app_name = "example-tgi-WizardCoder-Python-34B-V1.0"

generate = modal.Function.lookup(app_name, "Model.generate")
template = """\
Below is an instruction that describes a task. Think step-by-step and write a response that appropriately completes the request.

### Instruction:
{instruction}

Respond in the following format:

Step-by-step thoughts:
* Thought 1
* Thought 2

```
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
```

### Response:
"""
print(
    generate.remote(
        template.format(
            instruction="Write a fibonacci function mod p in O(logn) in Python. Write answer in triple backticks.\n"
        )
    )
)
