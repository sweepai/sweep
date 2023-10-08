import re


def find_function_calls(keyword: str, file_contents: str):
    spans = []
    if sum(c.isalnum() for c in keyword) <= 3:
        return spans  # avoid huge regex matches
    # regex_pattern = f"{re.escape(keyword)}\\s*\\((?:[^()]*|\\((?:[^()]*|\\([^()]*\\))*\\))*?\\)"
    # pattern = re.compile(regex_pattern, re.DOTALL)

    for match_ in re.finditer(re.escape(keyword), file_contents):
        parenthesis_count = 0
        is_function_call = False
        keyword_start = match_.end()
        print(f'"{file_contents[keyword_start]}"')
        for end_index, char in enumerate(
            file_contents[keyword_start:], start=keyword_start
        ):
            if char.isspace():
                print("here")
                continue
            if char == "(":
                is_function_call = True
                parenthesis_count += 1
            elif char == ")":
                parenthesis_count -= 1
            if parenthesis_count == 0:
                break
        else:
            print("continue")
            continue
        if is_function_call:
            start_line = file_contents.count("\n", 0, keyword_start)
            end_line = file_contents.count("\n", 0, end_index)
            spans.append((start_line, end_line + 1))

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
