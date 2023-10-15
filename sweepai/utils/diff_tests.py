import unittest
from unittest import mock
from loguru import logger
from sweepai.utils.diff import *

class TestDiff(unittest.TestCase):
    def test_diff_contains_dups_or_removals(self):
        diff = "diff"
        new_code = "new_code"
        self.assertFalse(diff_contains_dups_or_removals(diff, new_code))

        diff = "-old_line\n+new_line"
        new_code = "new_line\nnew_line"
        self.assertTrue(diff_contains_dups_or_removals(diff, new_code))

    def test_generate_diff(self):
        old_code = "old_code"
        new_code = "new_code"
        self.assertNotEqual(generate_diff(old_code, new_code), "")

        old_code = "same_code"
        new_code = "same_code"
        self.assertEqual(generate_diff(old_code, new_code), "")

    def test_revert_whitespace_changes(self):
        original_file_str = "original\nfile\nstring"
        modified_file_str = "modified\nfile\nstring"
        self.assertNotEqual(revert_whitespace_changes(original_file_str, modified_file_str), original_file_str)

        original_file_str = "same\nfile\nstring"
        modified_file_str = "same\nfile\nstring"
        self.assertEqual(revert_whitespace_changes(original_file_str, modified_file_str), original_file_str)

    def test_format_contents(self):
        # Existing test cases
        small_file = "line1\nline2\nline3\nline4\nline5"
        expected_output = "line1\nline2\nline3\nline4\nline5"
        self.assertEqual(format_contents(small_file), expected_output)

        markdown_file = "```python\ndef hello_world():\n    print('Hello, world!')\n```"
        expected_output = "def hello_world():\n    print('Hello, world!')"
        self.assertEqual(format_contents(markdown_file, is_markdown=True), expected_output)

        # Add more test cases here
        large_file = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10"
        expected_output = "line1\nline2\nline3\nline7\nline8\nline9\nline10"
        self.assertEqual(format_contents(large_file), expected_output)

    def test_generate_new_file(self):
        modify_file_response = "<new_file>\nnew_file_content\n</new_file>"
        old_file_content = "old_file_content"
        self.assertEqual(generate_new_file(modify_file_response, old_file_content), "new_file_content")

        modify_file_response = "<new_file>\n<copy_lines 1-1/>\n</new_file>"
        old_file_content = "old_file_content"
        self.assertEqual(generate_new_file(modify_file_response, old_file_content), "old_file_content")

    def test_match_string(self):
        original = "original_string"
        search = "original"
        self.assertEqual(match_string(original, search).score, 100)

        original = "original_string"
        search = "not_in_string"
        self.assertEqual(match_string(original, search).score, 0)

    def test_lstrip_max(self):
        s = "     string"
        chars = [" "]
        max_count = 3
        self.assertEqual(lstrip_max(s, chars, max_count), "  string")

        s = "\t\t\tstring"
        chars = ["\t"]
        max_count = 2
        self.assertEqual(lstrip_max(s, chars, max_count), "\tstring")

    def test_get_snippet_with_padding(self):
        original = ["original", "string"]
        best_match = Match(0, 2, 100)
        search = ["original", "string"]
        snippet, spaces, strip = get_snippet_with_padding(original, best_match, search)
        self.assertEqual(snippet, ["original", "string"])
        self.assertEqual(spaces, "")
        self.assertFalse(strip)

        original = ["    original", "    string"]
        best_match = Match(0, 2, 100)
        search = ["original", "string"]
        snippet, spaces, strip = get_snippet_with_padding(original, best_match, search)
        self.assertEqual(snippet, ["    original", "    string"])
        self.assertEqual(spaces, "    ")
        self.assertTrue(strip)

    def test_sliding_window_replacement(self):
        original = ["original", "string"]
        search = ["original"]
        replace = ["replacement"]
        self.assertEqual(sliding_window_replacement(original, search, replace)[0], ["replacement", "string"])

        original = ["original", "string"]
        search = ["not_in_string"]
        replace = ["replacement"]
        with self.assertRaises(Exception):
            sliding_window_replacement(original, search, replace)

    def test_get_all_diffs(self):
        modify_file_response = "<<<<\nold_code\n====\nnew_code\n>>>>"
        self.assertEqual(get_all_diffs(modify_file_response), "<<<<\nold_code\n====\nnew_code\n>>>>")

        modify_file_response = "no_diffs_here"
        self.assertEqual(get_all_diffs(modify_file_response), "")

    def test_get_matches(self):
        modify_file_response = "<<<<\nold_code\n====\nnew_code\n>>>>"
        self.assertEqual(get_matches(modify_file_response), [("old_code", "new_code")])

        modify_file_response = "no_matches_here"
        self.assertEqual(get_matches(modify_file_response), [])

    def test_generate_new_file_from_patch(self):
        modify_file_response = "<<<<\nold_code\n====\nnew_code\n>>>>"
        old_file_content = "old_code"
        self.assertEqual(generate_new_file_from_patch(modify_file_response, old_file_content)[0], "new_code")

        modify_file_response = "<<<<\nnot_in_old_code\n====\nnew_code\n>>>>"
        old_file_content = "old_code"
        self.assertEqual(generate_new_file_from_patch(modify_file_response, old_file_content)[0], "old_code")

    def test_join_contents_k(self):
        first = "line1\nline2\nline3"
        second = "line3\nline4\nline5"
        k = 1
        self.assertEqual(join_contents_k(first, second, k), "line1\nline2\nline3\nline4\nline5")

        first = "line1\nline2\nline3"
        second = "line4\nline5\nline6"
        k = 1
        self.assertEqual(join_contents_k(first, second, k), "line1\nline2\nline3\nline4\nline5\nline6")

    def test_is_markdown(self):
        # Existing test cases
        self.assertTrue(is_markdown("file.md"))
        self.assertTrue(is_markdown("file.rst"))
        self.assertTrue(is_markdown("file.txt"))
        self.assertFalse(is_markdown("file.py"))
        self.assertFalse(is_markdown("file.js"))

        # Add more test cases here
        self.assertTrue(is_markdown("file.markdown"))
        self.assertFalse(is_markdown("file.c"))
        self.assertFalse(is_markdown("file.java"))

if __name__ == "__main__":
    unittest.main()
