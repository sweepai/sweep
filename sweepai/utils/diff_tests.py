import unittest
from unittest.mock import patch
from sweepai.utils.diff import *

class TestDiffFunctions(unittest.TestCase):

    def test_format_contents(self):
        self.assertEqual(format_contents("", False), "")
        self.assertEqual(format_contents("```test```", False), "")
        self.assertEqual(format_contents("```test\ntest```", False), "test")
        self.assertEqual(format_contents("```test\ntest```", True), "test")
        self.assertEqual(format_contents("```test\ntest\ntest```", False), "test\ntest")
        self.assertEqual(format_contents("```test\ntest\ntest```", True), "test\ntest")
        self.assertEqual(format_contents("```test\nspecial characters !@#$%^&*()\ntest```", False), "test\nspecial characters !@#$%^&*()\ntest")
        self.assertEqual(format_contents("```test\nno markdown syntax\ntest```", True), "test\nno markdown syntax\ntest")

    def test_is_markdown(self):
        self.assertTrue(is_markdown("test.md"))
        self.assertTrue(is_markdown("test.rst"))
        self.assertTrue(is_markdown("test.txt"))
        self.assertFalse(is_markdown("test.py"))
        self.assertFalse(is_markdown(None))
        self.assertFalse(is_markdown(""))

    def test_diff_contains_dups_or_removals(self):
        self.assertFalse(diff_contains_dups_or_removals("a\nb\nc", "a\nb\nc"))
        self.assertTrue(diff_contains_dups_or_removals("a\nb\nc", "a\nb\nb\nc"))

    def test_lstrip_max(self):
        self.assertEqual(lstrip_max("   test", " ", 2), " test")
        self.assertEqual(lstrip_max("   test", " ", 0), "   test")

    def test_get_all_diffs(self):
        self.assertEqual(get_all_diffs("<<<<\na\n====\nb\n>>>>"), "<<<<\na\n====\nb\n>>>>")
        self.assertEqual(get_all_diffs(""), "")

    def test_generate_diff(self):
        self.assertEqual(generate_diff("a\nb\nc", "a\nb\nc"), "")
        self.assertNotEqual(generate_diff("a\nb\nc", "a\nb\nb\nc"), "")

    def test_revert_whitespace_changes(self):
        self.assertEqual(revert_whitespace_changes("a\nb\nc", " a\n b\n c"), "a\nb\nc")
        self.assertEqual(revert_whitespace_changes("a\nb\nc", "a\nb\n c"), "a\nb\nc")

    def test_generate_new_file(self):
        self.assertEqual(generate_new_file("<<<<\na\n====\nb\n>>>>", "a", 0), ("b", []))
        self.assertEqual(generate_new_file("<<<<\na\n====\nb\n>>>>", "c", 0), ("c", ["NO MATCHES FOUND\n```\na\n```\n\n```\nb\n```"]))

    def test_match_string(self):
        # Add test cases for match_string function
        self.assertEqual(match_string(["a", "b", "c"], ["b"]), Match(1, 2, 100))
        self.assertEqual(match_string(["a", "b", "c"], ["d"]), Match(0, 0, 0))

    def test_get_snippet_with_padding(self):
        # Add test cases for get_snippet_with_padding function
        self.assertEqual(get_snippet_with_padding(["a", "b", "c"], Match(1, 2, 100), ["b"]), (["b"], "", False))
        self.assertEqual(get_snippet_with_padding(["a", "b", "c"], Match(0, 0, 0), ["d"]), ([], "", False))

    def test_sliding_window_replacement(self):
        # Add test cases for sliding_window_replacement function
        self.assertEqual(sliding_window_replacement(["a", "b", "c"], ["b"], ["d"]), (["a", "d", "c"], Match(1, 2, 100), None))
        self.assertEqual(sliding_window_replacement(["a", "b", "c"], ["d"], ["e"]), (["a", "b", "c"], Match(0, 0, 0), None))

    def test_get_all_diffs(self):
        self.assertEqual(get_all_diffs("<<<<\na\n====\nb\n>>>>"), "<<<<\na\n====\nb\n>>>>")
        self.assertNotEqual(get_all_diffs("<<<<\na\n====\nb\n>>>>"), "<<<<\na\n====\nc\n>>>>")

    def test_get_matches(self):
        self.assertEqual(get_matches("<<<<\na\n====\nb\n>>>>"), [("a", "b")])
        self.assertNotEqual(get_matches("<<<<\na\n====\nb\n>>>>"), [("a", "c")])

    def test_generate_new_file_from_patch(self):
        # Add test cases for generate_new_file_from_patch function
        self.assertEqual(generate_new_file_from_patch("<<<<\na\n====\nb\n>>>>", "a", 0), ("b", []))
        self.assertEqual(generate_new_file_from_patch("<<<<\na\n====\nb\n>>>>", "c", 0), ("c", ["NO MATCHES FOUND\n```\na\n```\n\n```\nb\n```"]))

    def test_join_contents_k(self):
        self.assertEqual(join_contents_k("a\nb\nc", "b\nc\nd", 2), "a\nb\nc\nd")
        self.assertNotEqual(join_contents_k("a\nb\nc", "b\nc\nd", 2), "a\nb\nc\nb\nc\nd")

if __name__ == '__main__':
    unittest.main()
