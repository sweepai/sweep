import unittest
from unittest.mock import patch
from typing import List

from sweepai.utils.diff import (
    format_contents,
    is_markdown,
    match_string,
    revert_whitespace_changes,
)


class TestDiff(unittest.TestCase):
    def test_revert_whitespace_changes(self: 'TestDiff', original_file_str: str, modified_file_str: str) -> None:
        expected_output = "  line1\n  line2\n  line3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    def test_format_contents(self: 'TestDiff', file_contents: str) -> None:
        expected_output = "line1\nline2\nline3"
        self.assertEqual(format_contents(file_contents), expected_output)

    @patch("sweepai.utils.diff.find_best_match")
    def test_match_string(self: 'TestDiff', original: List[str], search: List[str]) -> None:
        mock_find_best_match.return_value = 1
        self.assertEqual(match_string(original, search), 1)

    def test_is_markdown(self: 'TestDiff', filename: str) -> None:
        self.assertTrue(is_markdown(filename))

if __name__ == "__main__":
    unittest.main()
