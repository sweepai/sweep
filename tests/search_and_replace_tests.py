import pytest

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
    assert score_line(" abc", "abc") < 100
    assert score_line("abc", "def") < 100


def test_match_without_whitespace():
    assert match_without_whitespace(" abc ", "abc")
    assert not match_without_whitespace("abc", "def")


def test_line_cost():
    assert line_cost("abc") < line_cost(" abc")
    assert line_cost("#abc") < line_cost("abc")


@pytest.mark.parametrize(
    "query, target, expected",
    [
        (["abc"], ["abc"], 100),
        (["abc"], ["def"], 0),
        (["abc", "def"], ["abc", "def"], 100),
        (["abc", "def"], ["def", "abc"], 0),
    ],
)
def test_score_multiline(query, target, expected):
    assert score_multiline(query, target) == expected


def test_Match():
    match = Match(0, 1, 100)
    assert match.start == 0
    assert match.end == 1
    assert match.score == 100


def test_get_indent_type():
    assert get_indent_type("  abc") == "  "
    assert get_indent_type("    abc") == "    "


def test_get_max_indent():
    assert get_max_indent("  abc\n    def", "  ") == 2
    assert get_max_indent("  abc\n    def", "    ") == 1


def test_find_best_match():
    assert find_best_match("abc", "abc").score == 100
    assert find_best_match("abc", "def").score == 0


def test_split_ellipses():
    assert split_ellipses("abc\n...\ndef") == ["abc", "def"]
    assert split_ellipses("abc\ndef") == ["abc\ndef"]
