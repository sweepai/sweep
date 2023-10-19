import unittest

from sweepai.utils.comment_utils import check_comments_presence


class TestCommentUtils(unittest.TestCase):
    def test_check_comments_presence(self):
        # Test Python file with a comment
        self.assertEqual(
            check_comments_presence("test.py", "# This is a comment"), True
        )

        # Test Python file without a comment
        self.assertEqual(
            check_comments_presence("test.py", 'print("Hello, World!")'), False
        )

        # Test JavaScript file with a comment
        self.assertEqual(
            check_comments_presence("test.js", "// This is a comment"), True
        )

        # Test JavaScript file without a comment
        self.assertEqual(
            check_comments_presence("test.js", 'console.log("Hello, World!");'), False
        )

        # Test unsupported file type with a comment
        self.assertEqual(
            check_comments_presence("test.txt", "# This is a comment"), False
        )

        # Test unsupported file type without a comment
        self.assertEqual(check_comments_presence("test.txt", "Hello, World!"), False)


if __name__ == "__main__":
    unittest.main()
