import unittest
from unittest.mock import patch
from sweepai.utils.diff import format_contents, is_markdown

class TestDiff(unittest.TestCase):

    def test_format_contents(self):
        # Test with markdown file
        file_contents = "```python\\nprint('Hello, World!')\\n```"
        self.assertEqual(format_contents(file_contents, True), "print('Hello, World!')")

        # Test with non-markdown file
        file_contents = "print('Hello, World!')"
        self.assertEqual(format_contents(file_contents, False), "print('Hello, World!')")

        # Test with empty file
        file_contents = ""
        self.assertEqual(format_contents(file_contents, False), "")

    def test_is_markdown(self):
        # Test with markdown file
        filename = "test.md"
        self.assertTrue(is_markdown(filename))

        # Test with non-markdown file
        filename = "test.py"
        self.assertFalse(is_markdown(filename))

        # Test with no extension
        filename = "test"
        self.assertFalse(is_markdown(filename))

if __name__ == "__main__":
    unittest.main()
