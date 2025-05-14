import re


def xml_pattern(
    tags: str,
    name: str | None = None,
    add_newlines: bool = True,
    **kwargs: dict[str, str],
) -> str:
    name = name or tags
    new_lines = "\n" if add_newlines else ""
    if kwargs:
        kwargs_pattern = "\s+" + r"\s+".join(
            rf"{key}=\"(?P<{value}>.*?)\"" for key, value in kwargs.items()
        )
    else:
        kwargs_pattern = ""
    return rf"<{tags}{kwargs_pattern}>{new_lines}(?P<{name}>.*?){new_lines}</{tags}>"


def search_xml(content: str, tag: str, **kwargs) -> str:
    return re.search(xml_pattern(tag, name=tag, **kwargs), content, re.DOTALL).group(
        tag
    )


if __name__ == "__main__":
    pattern = xml_pattern("additional_changes", required="additional_changes_required")
    print(pattern)
    example_template = """\
<additional_changes required="yes">
Test
</additional_changes>"""
    print(re.match(pattern, example_template))
