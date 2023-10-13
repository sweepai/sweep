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

    def test_is_markdown(self):
        self.assertTrue(is_markdown("test.md"))
        self.assertTrue(is_markdown("test.rst"))
        self.assertTrue(is_markdown("test.txt"))
        self.assertFalse(is_markdown("test.py"))

    def test_diff_contains_dups_or_removals(self):
        # Add test cases for diff_contains_dups_or_removals function

    def test_generate_diff(self):
        # Add test cases for generate_diff function

    def test_revert_whitespace_changes(self):
        # Add test cases for revert_whitespace_changes function

    def test_generate_new_file(self):
        # Add test cases for generate_new_file function

    def test_match_string(self):
        # Add test cases for match_string function

    def test_lstrip_max(self):
        # Add test cases for lstrip_max function

    def test_get_snippet_with_padding(self):
        # Add test cases for get_snippet_with_padding function

    def test_sliding_window_replacement(self):
        # Add test cases for sliding_window_replacement function

    def test_get_all_diffs(self):
        # Add test cases for get_all_diffs function

    def test_get_matches(self):
        # Add test cases for get_matches function

    def test_generate_new_file_from_patch(self):
        # Add test cases for generate_new_file_from_patch function

    def test_join_contents_k(self):
        # Add test cases for join_contents_k function

if __name__ == '__main__':
    unittest.main()
