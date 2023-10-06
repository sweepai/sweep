import tempfile

from sweepai.utils.search_and_replace import (
    Match,
    find_best_match,
    get_indent_type,
    get_max_indent,
    line_cost,
    match_without_whitespace,
    score_line,
    score_multiline,
    split_ellipses,
)


def test_score_line():
    assert score_line("abc", "abc") == 100
    assert score_line(" abc", "abc") == 90
    assert score_line("abc ", "abc") == 90
    assert score_line("abc", "def") < 100


def test_match_without_whitespace():
    assert match_without_whitespace("abc", "abc") is True
    assert match_without_whitespace(" abc", "abc") is True
    assert match_without_whitespace("abc", "def") is False


def test_line_cost():
    assert line_cost("abc") == 75
    assert line_cost(" #abc") == 80
    assert line_cost(" //abc") == 80
    assert line_cost("") == 50


def test_score_multiline():
    assert score_multiline(["abc"], ["abc"]) == 100
    assert score_multiline(["abc", "def"], ["abc", "def"]) == 100
    assert score_multiline(["abc", "def"], ["abc", "xyz"]) < 100


def test_Match():
    match = Match(0, 1, 100, "  ")
    assert match.start == 0
    assert match.end == 1
    assert match.score == 100
    assert match.indent == "  "


def test_get_indent_type():
    assert get_indent_type("  abc") == "  "
    assert get_indent_type("    abc") == "    "


def test_get_max_indent():
    assert get_max_indent("  abc", "  ") == 1
    assert get_max_indent("    abc", "  ") == 2


def test_find_best_match():
    with tempfile.NamedTemporaryFile(mode="w+t") as temp:
        temp.write("abc")
        temp.seek(0)
        assert find_best_match("abc", temp.name) == Match(0, 1, 100)
    with tempfile.NamedTemporaryFile(mode="w+t") as temp:
        temp.write("def")
        temp.seek(0)
        assert find_best_match("abc", temp.name) != Match(0, 1, 100)


def test_split_ellipses():
    assert split_ellipses("abc...def") == ["abc", "def"]
    assert split_ellipses("abc...def...ghi") == ["abc", "def", "ghi"]
