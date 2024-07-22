import unittest
import re
from fuzzywuzzy import fuzz
from sweepai.utils.search_and_replace import score_line, match_without_whitespace, line_cost, score_multiline, get_indent_type, get_max_indent, find_best_match, split_ellipses

class TestSearchAndReplace(unittest.TestCase):

    def test_score_line(self):
        self.assertEqual(score_line("abc", "abc"), 100)
        self.assertEqual(score_line(" abc", "abc"), 90)
        self.assertEqual(score_line("abc", " abc"), 90)
        self.assertEqual(score_line("abc", "def"), 0)

    def test_match_without_whitespace(self):
        self.assertTrue(match_without_whitespace("abc", "abc"))
        self.assertTrue(match_without_whitespace(" abc", "abc"))
        self.assertFalse(match_without_whitespace("abc", "def"))

    def test_line_cost(self):
        self.assertEqual(line_cost("abc"), 75)
        self.assertEqual(line_cost(" abc"), 75)
        self.assertEqual(line_cost("abc "), 75)
        self.assertEqual(line_cost(" abc "), 75)

    def test_score_multiline(self):
        self.assertEqual(score_multiline(["abc", "def"], ["abc", "def"]), 100)
        self.assertEqual(score_multiline(["abc", "def"], ["abc", "ghi"]), 50)
        self.assertEqual(score_multiline(["abc", "def"], ["ghi", "jkl"]), 0)

    def test_get_indent_type(self):
        self.assertEqual(get_indent_type("  abc\n    def"), "  ")
        self.assertEqual(get_indent_type("    abc\n  def"), "    ")

    def test_get_max_indent(self):
        self.assertEqual(get_max_indent("  abc\n    def", "  "), 2)
        self.assertEqual(get_max_indent("    abc\n  def", "    "), 1)

    def test_find_best_match(self):
        self.assertEqual(find_best_match("abc", "abc\ndef\nghi"), Match(0, 1, 100))
        self.assertEqual(find_best_match("def", "abc\ndef\nghi"), Match(1, 2, 100))
        self.assertEqual(find_best_match("ghi", "abc\ndef\nghi"), Match(2, 3, 100))

    def test_split_ellipses(self):
        self.assertEqual(split_ellipses("abc\n...\ndef\n...\nghi"), ["abc", "def", "ghi"])
        self.assertEqual(split_ellipses("abc\n...\ndef"), ["abc", "def"])
        self.assertEqual(split_ellipses("abc\n...\nghi"), ["abc", "ghi"])

if __name__ == '__main__':
    unittest.main()
