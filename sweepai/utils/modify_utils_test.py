import unittest
from sweepai.utils.modify_utils import parse_patch_into_hunks


class TestApplyUnifiedDiff(unittest.TestCase):
    def test_modify_lines(self):
        old_contents = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        patch = "-Line 2\n-Line 3\n+Line 2 Modified\n+Line 3 Modified\n-Line 4\n-Line 5\n+Line 4 Modified\n+Line 5 Modified"
        expected_result = [('Line 2\nLine 3\nLine 4\nLine 5', 'Line 2 Modified\nLine 3 Modified\nLine 4 Modified\nLine 5 Modified')]
        self.assertEqual(parse_patch_into_hunks(old_contents, patch), expected_result)

    def test_add_lines(self):
        old_contents = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        patch = "+Line 2.5\n+Line 2.6"
        expected_result = [("", "Line 2.5\nLine 2.6")]
        self.assertEqual(parse_patch_into_hunks(old_contents, patch), expected_result)

    def test_remove_lines(self):
        old_contents = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        patch = "-Line 3\n-Line 4"
        expected_result = [("Line 3\nLine 4", "")]
        self.assertEqual(parse_patch_into_hunks(old_contents, patch), expected_result)



if __name__ == '__main__':
    unittest.main()