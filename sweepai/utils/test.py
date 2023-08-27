import re

modify_file_response = """
<new_file>

wow

</new_file>"""

matches = re.findall(
    r"<new_file>\n(.*?)\n?</new_file>", modify_file_response, re.DOTALL
)[0]

print(matches)
