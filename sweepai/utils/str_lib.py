"""
p-string library for Python -- for quickly writing readable prompts
"""


class p(str):
    def __and__(self, other):
        return p(other if self else "")

    def __rand__(self, other):
        return p(other if self else "")

    def __or__(self, other):
        return p(self if self else other)

    def __ror__(self, other):
        return p(self if self else other)

    def __rshift__(self, other):
        return p((self + "\n\n" + other) if other else self)


# Examples snippets to clean up
"""
            changed_files_summary = "You have previously changed these files:\n" + "\n".join(
                [
                    f'<changed_file file_path="{file_path}">\n{diffs}\n</changed_file>'
                    for file_path, diffs in file_path_to_contents.items()
                ]
            )
"""

summary = p("")

print("summary", summary.strip().endswith("_No response_") & summary)

if __name__ == "__main__":
    name = p("Joe")

    # print(name & f"Hello {name}!")

    # guide = p("You are a helpful assistant.")

    # print(guide >> "Say this is a test!")

    # print(guide >> "")

    print("Hello" & p("World"))
