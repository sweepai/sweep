import re


def find_function_calls(keyword: str, file_contents: str):
    spans = []

    for match_ in re.finditer(re.escape(keyword), file_contents):
        parenthesis_count = 0
        is_function_call = False
        keyword_start = match_.end()
        for end_index, char in enumerate(
            file_contents[keyword_start:], start=keyword_start
        ):
            if char.isspace():
                continue
            if char == "(":
                is_function_call = True
                parenthesis_count += 1
            elif char == ")":
                parenthesis_count -= 1
            if parenthesis_count == 0:
                break
        else:
            continue
        if is_function_call:
            start_line = file_contents.count("\n", 0, keyword_start)
            end_line = file_contents.count("\n", 0, end_index)
            spans.append((start_line, end_line + 1))

    return spans
