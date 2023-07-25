from tabulate import tabulate

from sweepai.core.entities import FileChangeRequest

file_change_requests = [
    FileChangeRequest(
        filename="main.py",
        change_type="create",
        instructions="Do this\nthen that\nthen do\n```python\n#main {\nfont-size:12px\n}\n```"
    )
]

table = tabulate(
    [[f"`{file_change_request.filename}`", file_change_request.instructions.replace('\n', '<br/>').replace('```', '\\```')] for file_change_request in
        file_change_requests],
    headers=["File Path", "Proposed Changes"],
    tablefmt="pipe"
)

# assert table == """
# | File Path   | Proposed Changes                                                                               |
# |:------------|:-----------------------------------------------------------------------------------------------|
# | `main.py`   | Do this<br/>then that<br/>then do<br/>\```python<br/>#main {<br/>font-size:12px<br/>}<br/>\``` |
# """.strip()

print(table)