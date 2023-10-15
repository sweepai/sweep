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

    def test_format_contents(self):
        # Test with valid input
        input_str = "line1\nline2\nline3"
        expected_output = "line1\nline2\nline3"
        self.assertEqual(format_contents(input_str), expected_output)

        # Test with invalid input
        input_str = 123
        self.assertRaises(TypeError, format_contents, input_str)

    def test_is_markdown(self):
        # Test with markdown string
        input_str = "# Heading"
        self.assertTrue(is_markdown(input_str))

        # Test with non-markdown string
        input_str = "Not a heading"
        self.assertFalse(is_markdown(input_str))

    def test_match_string(self):
        # Test with matching strings
        str1 = "Hello, world!"
        str2 = "Hello, world!"
        self.assertTrue(match_string(str1, str2))

        # Test with non-matching strings
        str1 = "Hello, world!"
        str2 = "Goodbye, world!"
        self.assertFalse(match_string(str1, str2))


if __name__ == "__main__":
    unittest.main()

    


if __name__ == "__main__":
    unittest.main()
