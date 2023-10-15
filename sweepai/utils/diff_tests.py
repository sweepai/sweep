import unittest
from unittest.mock import patch

from sweepai.utils.diff import (
    format_contents,
    is_markdown,
    match_string,
    revert_whitespace_changes,
)


class TestDiff(unittest.TestCase):
    def test_revert_whitespace_changes(self):
        original_file_str = "  line1\n  line2\n  line3"
        modified_file_str = "line1\n  line2\n    line3"
        expected_output = "  line1\n  line2\n  line3"
        self.assertEqual(
            revert_whitespace_changes(original_file_str, modified_file_str),
            expected_output,
        )

    


if __name__ == "__main__":
    unittest.main()
