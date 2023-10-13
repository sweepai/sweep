import unittest
import unittest.mock
from sweepai.utils.diff import format_contents, is_markdown, diff_contains_dups_or_removals, generate_diff, revert_whitespace_changes, generate_new_file, match_string, get_snippet_with_padding, sliding_window_replacement, get_all_diffs, get_matches, generate_new_file_from_patch, join_contents_k

class TestDiff(unittest.TestCase):
    def test_format_contents(self):
        # Mocking the is_markdown function as it is a dependency for format_contents
        with unittest.mock.patch('sweepai.utils.diff.is_markdown', return_value=False):
            result = format_contents("test\ncontent\n")
            self.assertEqual(result, "test\ncontent\n")

    def test_is_markdown(self):
        result = is_markdown("test.md")
        self.assertTrue(result)

    def test_diff_contains_dups_or_removals(self):
        diff = "-line1\n+line1\n+line1\n"
        new_code = "line1\nline1\n"
        result = diff_contains_dups_or_removals(diff, new_code)
        self.assertTrue(result)

    def test_generate_diff(self):
        old_code = "line1\nline2\n"
        new_code = "line1\nline3\n"
        result = generate_diff(old_code, new_code)
        self.assertEqual(result, "-line2\n+line3\n")

    def test_revert_whitespace_changes(self):
        original_file_str = "line1\nline2\n"
        modified_file_str = "line1  \nline2  \n"
        result = revert_whitespace_changes(original_file_str, modified_file_str)
        self.assertEqual(result, original_file_str)

    def test_generate_new_file(self):
        modify_file_response = "<new_file>\nline1\nline2\n</new_file>"
        old_file_content = "line1\nline2\n"
        result = generate_new_file(modify_file_response, old_file_content)
        self.assertEqual(result, old_file_content)

    def test_match_string(self):
        original = "line1\nline2\n"
        search = "line2"
        result = match_string(original, search)
        self.assertEqual(result.start, 1)
        self.assertEqual(result.end, 2)

    def test_get_snippet_with_padding(self):
        original = "line1\nline2\nline3\n"
        best_match = match_string(original, "line2")
        search = "line2"
        snippet, spaces, strip = get_snippet_with_padding(original, best_match, search)
        self.assertEqual(snippet, ["line2"])
        self.assertEqual(spaces, "")
        self.assertFalse(strip)

    def test_sliding_window_replacement(self):
        original = ["line1", "line2", "line3"]
        search = ["line2"]
        replace = ["line4"]
        result, best_match, status = sliding_window_replacement(original, search, replace)
        self.assertEqual(result, ["line1", "line4", "line3"])

    def test_get_all_diffs(self):
        modify_file_response = "<<<<\nline1\n====\nline2\n>>>>"
        result = get_all_diffs(modify_file_response)
        self.assertEqual(result, "line1\n====\nline2")

    def test_get_matches(self):
        modify_file_response = "<<<<\nline1\n====\nline2\n>>>>"
        result = get_matches(modify_file_response)
        self.assertEqual(result, [("line1", "line2")])

    def test_generate_new_file_from_patch(self):
        modify_file_response = "<<<<\nline1\n====\nline2\n>>>>"
        old_file_content = "line1\n"
        chunk_offset = 0
        result, errors = generate_new_file_from_patch(modify_file_response, old_file_content, chunk_offset)
        self.assertEqual(result, "line2\n")
        self.assertEqual(errors, [])

    def test_join_contents_k(self):
        first = "line1\nline2\n"
        second = "line2\nline3\n"
        k = 1
        result = join_contents_k(first, second, k)
        self.assertEqual(result, "line1\nline2\nline3\n")

if __name__ == '__main__':
    unittest.main()
