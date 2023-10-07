import unittest
from sweepai.utils.search_and_replace import score_line, match_without_whitespace, line_cost, score_multiline, get_indent_type, get_max_indent, find_best_match, split_ellipses

class TestSearchAndReplace(unittest.TestCase):

    def test_score_line(self):
        self.assertEqual(score_line("test", "test"), 100)
        self.assertEqual(score_line(" test", "test"), 90)
        self.assertEqual(score_line("test ", "test"), 90)
        self.assertEqual(score_line("test", "Test"), 70)
        self.assertEqual(score_line("test", ""), 0)

    def test_match_without_whitespace(self):
        self.assertTrue(match_without_whitespace("test", "test"))
        self.assertTrue(match_without_whitespace(" test", "test"))
        self.assertTrue(match_without_whitespace("test ", "test"))
        self.assertFalse(match_without_whitespace("test", "Test"))

    def test_line_cost(self):
        self.assertEqual(line_cost(""), 50)
        self.assertEqual(line_cost(" # comment"), 80)
        self.assertEqual(line_cost("test"), 90)

    def test_score_multiline(self):
        self.assertEqual(score_multiline(["test"], ["test"]), 100)
        self.assertEqual(score_multiline(["test", "test"], ["test", "test"]), 100)
        self.assertEqual(score_multiline(["test", "test"], ["test", "Test"]), 85)

    def test_get_indent_type(self):
        self.assertEqual(get_indent_type("  test\n    test"), "  ")
        self.assertEqual(get_indent_type("    test\n  test"), "    ")

    def test_get_max_indent(self):
        self.assertEqual(get_max_indent("  test\n    test", "  "), 2)
        self.assertEqual(get_max_indent("    test\n  test", "    "), 1)

    def test_find_best_match(self):
        self.assertEqual(find_best_match("test", "test"), Match(0, 1, 100))
        self.assertEqual(find_best_match("test", "Test"), Match(0, 1, 70))

    def test_split_ellipses(self):
        self.assertEqual(split_ellipses("test\n...\ntest"), ["test", "test"])
        self.assertEqual(split_ellipses("test\n...\nTest"), ["test", "Test"])

if __name__ == "__main__":
    unittest.main()
