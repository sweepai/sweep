from fuzzywuzzy import fuzz


def score_line(str1: str, str2: str) -> float:
    if str1 == str2:
        return 100

    if str1.lstrip() == str2.lstrip():
        whitespace_ratio = abs(len(str1) - len(str2)) / (len(str1) + len(str2))
        score = 90 - whitespace_ratio * 10
        return max(score, 0)

    if str1.strip() == str2.strip():
        whitespace_ratio = abs(len(str1) - len(str2)) / (len(str1) + len(str2))
        score = 80 - whitespace_ratio * 10
        return max(score, 0)

    levenshtein_ratio = fuzz.ratio(str1, str2)

    score = 70 * (levenshtein_ratio / 100)
    return max(score, 0)


def match_without_whitespace(str1: str, str2: str) -> bool:
    return str1.strip() == str2.strip()


def score_multiline(query: list[str], target: list[str]) -> float:
    # TODO: add weighting on first and last lines

    q, t = 0, 0  # indices for query and target
    scores = []
    skipped_comments = 0

    while q < len(query) and t < len(target):
        print(q, t)
        q_line = query[q]
        t_line = target[t]

        if match_without_whitespace(q_line, t_line):
            # Case 1: lines match
            scores.append(score_line(q_line, t_line))
            q += 1
            t += 1
        elif (
            t_line.strip() == ""
            and t_line.strip().startswith("#")
            or t_line.strip().startswith("//")
        ):
            # Case 2: skipped comment
            skipped_comments += 1
            q += 1
            t += 2
        elif q_line.strip() == "...":
            # Case 3: ellipsis wildcard
            lines_matched = 1
            t += 1
            if q + 1 == len(query):
                scores.append(100 - (len(target) - t))
                break
            while t < len(target) and not match_without_whitespace(
                query[q + 1], target[t]
            ):
                lines_matched += 1
                t += 1
            if t == len(target):
                return 0
            q += 1
            scores.append(100 - lines_matched)
        else:
            return 0

    print(scores)
    final_score = sum(scores) / len(scores) if scores else 0
    final_score *= 1 - 0.05 * skipped_comments

    return final_score


def find_best_match(target: str, code_file: str):
    best_score = 0
    best_span = None

    lines = code_file.split("\n")
    target_lines = target.split("\n")

    for i in range(len(lines)):
        for j in range(i + len(target_lines), len(lines) + 1):
            candidate = lines[i:j]
            score = fuzz.partial_ratio(target_lines, candidate)

            # Weigh missing comments less
            if any(line.strip().startswith("#") for line in target_lines):
                score *= 0.9

            # Ellipses match anything, prefer shorter
            if "..." in target:
                score *= 1 - 0.01 * abs(len(candidate) - len(target_lines))

            # Weigh errors on edge lines more
            edge_weight = 2
            for k in range(len(target_lines) // 2):
                if (
                    target_lines[k] != candidate[k]
                    or target_lines[-(k + 1)] != candidate[-(k + 1)]
                ):
                    score *= 1 - 0.05 * edge_weight
                edge_weight -= 0.2

            if score > best_score:
                best_score = score
                best_span = (i, j - 1)

    return best_span


query = """\
foo()
print("hello world")
...
bar()\
"""

target = """\
foo()
// this is a comment
print("hello world")
xyz()
test()
bar()\
"""

query = """\
foo()
print("hello world")
...\
"""

target = """\
foo()
// this is a comment
print("hello world")
xyz()
test()\
"""

print(score_multiline(query.split("\n"), target.split("\n")))

# code_file = """
# # Import libraries
# import os
# import sys

# # Initialize
# def initialize():
#     print("Initializing...")
#     x = 1
#     y = 2
#     print("Done!")

# # Main function
# def main():
#     print("Hello, World!")
# """

# # Sample target snippet
# target = """
# # Initialize
# def initialize():
#     ...
#     print("Done!")
# """.strip()

# # Find the best match
# best_span = find_best_match(target, code_file)
# print(f"Best match line numbers: {best_span}")

# if __name__ == "__main__":
#     string1 = "hello world"
#     string2 = "hello   world!"

#     string1 = "     hello world"
#     string2 = "hello world"

#     score = line_scoring(string1, string2)
#     print(f"Score: {score}%")
