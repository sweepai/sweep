"""
p-string library for Python -- for quickly writing readable prompts
"""

from typing import Iterator


class p(str):
    def __and__(self, other):
        return p(other if self else "")

    def __rand__(self, other):
        return p(other if self else "")

    def __or__(self, other):
        return p(self if self else other)

    def __ror__(self, other):
        return p(self if self else other)

    def __add__(self, other):
        return p(super().__add__(other))

    def __rshift__(self, other):
        return p((self + "\n" + other) if other else self)

    @staticmethod
    def map_format(template: str, iterable: Iterator[str], delimiter="\n"):
        """
        Applies a formatting template to each item in an iterable.
        The template should be a string suitable for str.format() method or an f-string expression.
        """
        return p(
            delimiter.join(
                [
                    (
                        template.format(*item)
                        if isinstance(item, tuple)
                        else template.format(item)
                    )
                    for item in iterable
                ]
            )
        )


# Examples snippets to clean up
"""
            changed_files_summary = "You have previously changed these files:\n" + "\n".join(
                [
                    f'<changed_file file_path="{file_path}">\n{diffs}\n</changed_file>'
                    for file_path, diffs in file_path_to_contents.items()
                ]
            )
"""

file_paths_to_contents = {
    "file1.py": "contents1",
}

relevant_files_summary = p("Relevant files in this PR:") >> p.map_format(
    p('<changed_file file_path="{}">') >> "{}" >> "</changed_file>",
    file_paths_to_contents.items(),
)

relevant_files_summary = p("Relevant files in this PR:") >> file_paths_to_contents.map(
    lambda file_path, file_contents: p(
        f'<changed_file file_path="{file_path}">\n{file_contents}\n</changed_file>'
    )
)

print(relevant_files_summary)


"""
                    relevant_files_summary = "Relevant files in this PR:\n\n" + "\n".join(
                        [
                            f'<relevant_file file_path="{file_path}">\n{file_contents}\n</relevant_file>'
                            for file_path, file_contents in zip(
                                file_change_request.relevant_files,
                                relevant_files_contents,
                            )
                        ]
                    )
"""

summary = p("")

# print("summary", summary.strip().endswith("_No response_") & summary)

if __name__ == "__main__":
    name = p("Joe")

    # print(name & f"Hello {name}!")

    # guide = p("You are a helpful assistant.")

    # print(guide >> "Say this is a test!")

    # print(guide >> "")

    # print("Hello" & p("World"))
