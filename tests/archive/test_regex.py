import re

# pattern = "- \[[X ]\] `(?P<filename>.*?)`(?P<instructions>.*?)(?=- \[[X ]\]|</details>)"
pattern = "- \[[X ]\] `(?P<filename>.*?)`(?P<instructions>.*?)(?=- \[[X ]\]|</details>)"
pattern_checklist = (
    "<details>\n<summary>Checklist</summary>(?P<checklist>.*?)</details>"
)

data = """
<details>
<summary>Checklist</summary>

- [X] `sweepai/handlers/on_ticket.py`
> * After the line where `repo = g.get_repo(repo_full_name)`, add a new line to get the number of files in the repository. You can use the `get_num_files_from_repo` function from `sweepai/utils/github_utils.py` for this. Store the result in a variable named `num_of_files`.
> • Add a conditional statement to check if `num_of_files` is zero. If it is, call the `edit_sweep_comment` function with a message stating that Sweep doesn't work on empty repositories. You can use the existing calls to `edit_sweep_comment` in the `on_ticket` function as a reference for how to call this function.
> • After calling `edit_sweep_comment`, add a `return` statement to exit the function early.

- [X] `sweepai/handlers/on_ticket.py`
> * After the line where `repo = g.get_repo(repo_full_name)`, add a new line to get the number of files in the repository. You can use the `get_num_files_from_repo` function from `sweepai/utils/github_utils.py` for this. Store the result in a variable named `num_of_files`.
> • Add a conditional statement to check if `num_of_files` is zero. If it is, call the `edit_sweep_comment` function with a message stating that Sweep doesn't work on empty repositories. You can use the existing calls to `edit_sweep_comment` in the `on_ticket` function as a reference for how to call this function.
> • After calling `edit_sweep_comment`, add a `return` statement to exit the function early.
</details>
"""

data = """
<details>
<summary>Checklist</summary>

- [X] `calculator.py`
> * Add a new function at the top of the file, after the divide function and before the calculator function. Name this function exponent, and make it take two arguments, base and exponent. In the body of the function, return the result of base raised to the power of exponent.
> • In the calculator function, add a new print statement after the print statement for the Divide operation, to display a new option for the Exponent operation.
> • After the if statement that handles the Divide operation, add a new elif statement to handle the Exponent operation. In this statement, call the exponent function with num1 and num2 as arguments, and assign the result to a variable named result. Then, print the result in the same format as the other operations.

</details>
"""

checklist_raw = re.search(pattern_checklist, data, re.DOTALL).group(0)
# print(checklist_raw)
for filename, instructions in re.findall(pattern, checklist_raw, re.DOTALL):
    print(filename, instructions)
    # print(_match.group("instructions"))
