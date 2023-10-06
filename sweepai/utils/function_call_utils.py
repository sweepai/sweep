import re


def find_function_calls(keyword: str, file_contents: str):
    spans = []
    if sum(c.isalnum() for c in keyword) <= 3:
        return spans # avoid huge regex matches
    pattern = re.compile(
        f"{re.escape(keyword)}\\s*\\(([^()]*|\\([^()]*\\))*\\)", re.DOTALL
    )

    for match_ in pattern.finditer(file_contents):
        start, end = match_.span()
        start_line = file_contents.count("\n", 0, start)
        end_line = file_contents.count("\n", 0, end)
        spans.append((start_line, end_line))

    return spans


file_contents = """\
    call_this(
        x,
        y
    )
    dontcallthis
    call_this(inside())
"""

if __name__ == "__main__":
    keyword = "call_this"
    print(find_function_calls(keyword, file_contents))
