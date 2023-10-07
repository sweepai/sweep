import unittest
from unittest.mock import patch
from sweepai.utils.search_and_replace import (
    score_line,
    match_without_whitespace,
    line_cost,
    score_multiline,
    get_indent_type,
    get_max_indent,
    find_best_match,
    split_ellipses,
    Match,
)


class TestSearchAndReplace(unittest.TestCase):
    def test_score_line(self):
        self.assertEqual(score_line("abc", "abc"), 100)
        self.assertEqual(score_line(" abc", "abc"), 90)
        self.assertEqual(score_line("abc ", "abc"), 90)
        self.assertEqual(score_line(" abc ", "abc"), 80)
        self.assertEqual(score_line("abc", "abcd"), 70)

    def test_match_without_whitespace(self):
        self.assertTrue(match_without_whitespace("abc", "abc"))
        self.assertTrue(match_without_whitespace(" abc", "abc"))
        self.assertTrue(match_without_whitespace("abc ", "abc"))
        self.assertTrue(match_without_whitespace(" abc ", "abc"))
        self.assertFalse(match_without_whitespace("abc", "abcd"))

    def test_line_cost(self):
        self.assertEqual(line_cost("abc"), 75)
        self.assertEqual(line_cost(" abc"), 80)
        self.assertEqual(line_cost("abc "), 80)
        self.assertEqual(line_cost(" abc "), 85)
        self.assertEqual(line_cost("#abc"), 80)
        self.assertEqual(line_cost("//abc"), 80)
        self.assertEqual(line_cost(""), 50)

    def test_score_multiline(self):
        self.assertEqual(score_multiline(["abc"], ["abc"]), 100)
        self.assertEqual(score_multiline(["abc", "def"], ["abc", "def"]), 100)
        self.assertEqual(score_multiline(["abc", "...", "def"], ["abc", "ghi", "def"]), 100)
        self.assertEqual(score_multiline(["abc", "...", "def"], ["abc", "ghi", "jkl"]), 50)

    def test_get_indent_type(self):
        self.assertEqual(get_indent_type("  abc\n    def"), "  ")
        self.assertEqual(get_indent_type("    abc\n  def"), "    ")

    def test_get_max_indent(self):
        self.assertEqual(get_max_indent("  abc\n    def", "  "), 2)
        self.assertEqual(get_max_indent("    abc\n  def", "    "), 1)

    def test_find_best_match(self):
        self.assertEqual(find_best_match("abc", "abc\nabc"), Match(0, 1, 100))
        self.assertEqual(find_best_match("abc", "def\nabc"), Match(1, 2, 100))
        self.assertEqual(find_best_match("abc", "def\nghi"), Match(-1, -1, 0))

    def test_split_ellipses(self):
        self.assertEqual(split_ellipses("abc\n...\ndef"), ["abc", "def"])
        self.assertEqual(split_ellipses("abc\n...\ndef\n...\nghi"), ["abc", "def", "ghi"])

    def test_Match(self):
        match = Match(0, 1, 100)
        self.assertEqual(match.start, 0)
        self.assertEqual(match.end, 1)
        self.assertEqual(match.score, 100)

    


if __name__ == "__main__":
    unittest.main()
