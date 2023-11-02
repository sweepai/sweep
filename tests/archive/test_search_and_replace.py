from sweepai.utils.search_and_replace import score_multiline

search_code = open("tests/archive/search_code.txt").read()
replace_code = open("tests/archive/replace_code.txt").read()

print(score_multiline(search_code.splitlines(), replace_code.splitlines()))
print(score_multiline(replace_code.splitlines(), search_code.splitlines()))
