# Note to contributors: This is an implementation of fuzzy diff.
# It's a bit broken so if you have a better implementation, please replace this.
# Based on https://blog.jcoglan.com/2017/09/19/the-patience-diff-algorithm/

# TODO: Improve this with Hungarian method to find the best matches
# treating the matches as an assignment problem.
# Minimize the product of the fuzziness scores. We can take the negative
# log of the fuzziness scores and use that as the cost matrix.

import re
from rapidfuzz import fuzz

THRESHOLD = 95

def similar(a: str, b: str):
    # Replace all runs of over 3 spaces to 3 spaces using regex
    a = re.sub(r"\s{4,}", "   ", a)
    b = re.sub(r"\s{4,}", "   ", b)
    return fuzz.ratio(a, b) > THRESHOLD

def lis(lst: list):
    # Longest increasing subsequence
    # Patience sorting algorithm
    if not lst:
        return []

    dag = {lst[0]: None}
    buckets = [[lst[0]]]
    
    for i, x in enumerate(lst[1:]):
        # Should use binary search here for O(nlogn) but quadratic for now
        # Haven't seen performance issues yet
        for j, bucket in enumerate(buckets):
            if x < bucket[-1]:
                buckets[j].append(x)
                dag[x] = buckets[j - 1][-1] if j > 0 else None
                break
        else:
            buckets.append([x])
            dag[x] = buckets[-2][-1]
        
    result = []
    k = buckets[-1][-1]
    while k is not None:
        result.append(k)
        k = dag[k]

    back_map = {x: i for i, x in enumerate(lst)}
    return [back_map[x] for x in result[::-1]]

def find_unique_matches(
    old_lines: list,
    new_lines: list
):
    matched_lines = set()
    matches = []
    for i, old_line in enumerate(old_lines):
        if old_line in old_lines[:i] or old_line in old_lines[i + 1:]:
            continue
        max_index = -1
        max_fuzz = 0
        for j, new_line in enumerate(new_lines):
            if j in matched_lines:
                continue
            ratio = fuzz.ratio(old_line, new_line)
            if ratio > max_fuzz:
                max_fuzz = ratio
                max_index = j
        if max_fuzz > THRESHOLD:
            matches.append((i, max_index))
            matched_lines.add(max_index)
    return matches


def patience_fuzzy_diff_lines(
    old_lines: list[str],
    new_lines: list[str]
) -> str:
    # Assumes new string has a few lines added from old string.
    # There's probably a better implementation but we'll do this for now.
    if not old_lines:
        return [f"+ {line}" for line in new_lines]
    if not new_lines:
        return [f"- {line}" for line in old_lines]
    if len(old_lines) == len(new_lines) and all(similar(old_line, new_line) for old_line, new_line in zip(old_lines, new_lines)):
        return [f"  {line}" for line in new_lines]
    diff_lines = []
    matches = find_unique_matches(old_lines, new_lines)
    match_indices = lis([right for _left, right in matches])
    matches = [matches[i] for i in match_indices]
    if matches:
        last_left, last_right = 0, 0
        for left, right in matches:
            current_left_lines = old_lines[last_left:left]
            current_right_lines = new_lines[last_right:right]

            diff_lines.extend(patience_fuzzy_diff_lines(current_left_lines, current_right_lines))
            diff_lines.append(f"  {new_lines[right]}")

            last_left = left + 1
            last_right = right + 1
        diff_lines.extend(patience_fuzzy_diff_lines(old_lines[last_left:], new_lines[last_right:]))
    else:
        if similar(old_lines[0], new_lines[0]):
            diff_lines.append(f"  {new_lines[0]}")
        else:
            diff_lines.append(f"- {old_lines[0]}")
            diff_lines.append(f"+ {new_lines[0]}")
        diff_lines.extend(patience_fuzzy_diff_lines(old_lines[1:], new_lines[1:]))
    return diff_lines

def patience_fuzzy_diff(
    old_string: str,
    new_string: str
):
    if old_string == new_string:
        return ""
    old_lines = old_string.splitlines()
    new_lines = new_string.splitlines()
    diff_lines = patience_fuzzy_diff_lines(old_lines, new_lines)
    return "\n".join(diff_lines)

def patience_fuzzy_additions(
    old_string: str,
    new_string: str
):
    if old_string == new_string:
        return ""
    old_lines = old_string.splitlines()
    new_lines = new_string.splitlines()
    diff_lines = patience_fuzzy_diff_lines(old_lines, new_lines)
    return "\n".join(line[2:] for line in diff_lines if line.startswith("+"))

old_lint_results = """> pylint sweepai/handlers/on_ticket.py

************* Module on_ticket
sweepai/handlers/on_ticket.py:167:52: W0613: Unused argument 'reaction_content' (unused-argument)
sweepai/handlers/on_ticket.py:221:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:251:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:268:34: W0612: Unused variable 'user_message' (unused-variable)
sweepai/handlers/on_ticket.py:525:16: W0719: Raising too general exception: Exception (broad-exception-raised)"""

old_lint_results = """src/components/CallToAction.tsx
    1:1   error  Definition for rule 'import/first' was not found  import/first
   16:14  error  Require statement not part of import statement    @typescript-eslint/no-var-requires
   24:5   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
   25:7   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
   33:9   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
   81:9   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
   87:18  error  'React' must be in scope when using JSX           react/react-in-jsx-scope
  117:9   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
  125:9   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
  137:9   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
  149:9   error  'React' must be in scope when using JSX           react/react-in-jsx-scope
  150:11  error  'React' must be in scope when using JSX           react/react-in-jsx-scope
  151:13  error  'React' must be in scope when using JSX           react/react-in-jsx-scope

✖ 13 problems (13 errors, 0 warnings)"""

new_lint_results = """> pylint sweepai/handlers/on_ticket.py

************* Module on_ticket
sweepai/handlers/on_ticket.py:167:52: W0613: Unused argument 'reaction_content' (unused-argument)
sweepai/handlers/on_ticket.py:245:12: W0621: Redefining name 'logger' from outer scope (line 23) (redefined-outer-name)
sweepai/handlers/on_ticket.py:221:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:245:21: E0602: Undefined variable 'Logger' (undefined-variable)
sweepai/handlers/on_ticket.py:252:24: W3101: Missing timeout argument for method 'requests.get' can cause your program to hang indefinitely (missing-timeout)
sweepai/handlers/on_ticket.py:269:34: W0612: Unused variable 'user_message' (unused-variable)
sweepai/handlers/on_ticket.py:526:16: W0719: Raising too general exception: Exception (broad-exception-raised)"""

new_lint_results = """src/components/CallToAction.tsx
    1:1   error  Definition for rule 'import/first' was not found                 import/first
   16:14  error  Require statement not part of import statement                   @typescript-eslint/no-var-requires
   24:5   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
   25:7   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
   33:9   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
   81:9   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
   87:18  error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
  117:9   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
  125:10  error  'FaPhone' is not defined                                         no-undef
  125:25  error  `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`  react/no-unescaped-entities
  125:40  error  `'` can be escaped with `&apos;`, `&lsquo;`, `&#39;`, `&rsquo;`  react/no-unescaped-entities
  127:9   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
  136:21  error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
  136:22  error  'FaPhone' is not defined                                         react/jsx-no-undef
  136:22  error  'FaPhone' is not defined                                         no-undef
  140:9   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
  152:9   error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
  153:11  error  'React' must be in scope when using JSX                          react/react-in-jsx-scope
  154:13  error  'React' must be in scope when using JSX                          react/react-in-jsx-scope

✖ 19 problems (19 errors, 0 warnings)"""

# old_lint_results = """David Axelrod
# Electric Prunes
# Gil Scott Heron
# The Slits
# Faust
# The Sonics
# The Sonics"""

# new_lint_results = """The Slits
# Electric Prunes
# Gil Scott Heron
# David Axelrod
# Electric Prunes
# Faust
# The Sonics
# The Sonics"""

stress_test_old = "AAGTCCGTAACCTGACATCTGAGGCTAATCACTGAGGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGAT"
stress_test_new = "AAGTCCGTAACCTGACATCTGAGGCTAATCACTGAGGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGATATGCGTATGCGCGAT"

if __name__ == "__main__":
    import time
    start = time.time()
    # print(patience_fuzzy_diff(
    #     old_lint_results,
    #     new_lint_results
    # ))
    print(patience_fuzzy_additions(
        old_lint_results,
        new_lint_results
    ))
    print(f"Time taken: {time.time() - start} seconds.")
