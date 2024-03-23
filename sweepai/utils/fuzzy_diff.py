# Note to contributors: This is a naive implementation of a fuzzy diff.
# It's a bit broken and assumes a lot of things but if you have a better implementation, please replace this.

from rapidfuzz import fuzz

def naive_fuzzy_diff(
    old_string: str,
    new_string: str
) -> str:
    # Assumes new string has a few lines added from old string.
    # There's probably a better implementation but we'll do this for now.
    if old_string == new_string:
        return ""
    old_lines = old_string.splitlines()
    new_lines = new_string.splitlines()
    old_len = len(old_lines)
    new_len = len(new_lines)
    i, j = 0, 0
    added_lines = []
    removed_lines = []
    while i < old_len and j < new_len:
        ratio = fuzz.ratio(old_lines[i], new_lines[j])

        if ratio < 90:
            added_lines.append(new_lines[j])
            j += 1
            continue
        else:
            i += 1
            j += 1
    return "\n".join(added_lines)

old_lint_results = """
> pylint sweepai/handlers/on_ticket.py

************* Module on_ticket
sweepai/handlers/on_ticket.py:167:52: W0613: Unused argument 'reaction_content' (unused-argument)
sweepai/handlers/on_ticket.py:221:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:251:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:268:34: W0612: Unused variable 'user_message' (unused-variable)
sweepai/handlers/on_ticket.py:525:16: W0719: Raising too general exception: Exception (broad-exception-raised)
"""

new_line_results = """
> pylint sweepai/handlers/on_ticket.py

************* Module on_ticket
sweepai/handlers/on_ticket.py:167:52: W0613: Unused argument 'reaction_content' (unused-argument)
sweepai/handlers/on_ticket.py:245:12: W0621: Redefining name 'logger' from outer scope (line 23) (redefined-outer-name)
sweepai/handlers/on_ticket.py:221:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:245:21: E0602: Undefined variable 'Logger' (undefined-variable)
sweepai/handlers/on_ticket.py:252:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:269:34: W0612: Unused variable 'user_message' (unused-variable)
sweepai/handlers/on_ticket.py:526:16: W0719: Raising too general exception: Exception (broad-exception-raised)
"""

if __name__ == "__main__":
    naive_fuzzy_diff(old_lint_results, new_line_results)
