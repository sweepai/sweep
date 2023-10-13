import unittest
from unittest.mock import patch
from sweepai.utils.diff import format_contents, is_markdown

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

if __name__ == '__main__':
    unittest.main()
