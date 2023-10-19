import unittest

from sweepai.utils.comment_utils import check_comments_presence


class TestCommentUtils(unittest.TestCase):
    def test_check_comments_presence(self):
        # Test unsupported file type without a comment
        self.assertEqual(check_comments_presence("test.txt", "Hello, World!"), False)

    def test_check_comments_presence_edge_cases(self):
        # Test Python file with a single-line comment
        self.assertEqual(
            check_comments_presence("test.py", "# This is a single-line comment"), True
        )

        # Test Python file with a multiline comment
        self.assertEqual(
            check_comments_presence("test.py", "'''This is a multiline comment'''"), True
        )

        # Test Python file with a comment that contains code
        self.assertEqual(
            check_comments_presence("test.py", "# print('Hello, World!')"), True
        )

        # Test JavaScript file with a single-line comment
        self.assertEqual(
            check_comments_presence("test.js", "// This is a single-line comment"), True
        )

        # Test JavaScript file with a multiline comment
        self.assertEqual(
            check_comments_presence("test.js", "/* This is a multiline comment */"), True
        )

        # Test JavaScript file with a comment that contains code
        self.assertEqual(
            check_comments_presence("test.js", "// console.log('Hello, World!');"), True
        )

        # Test unsupported file type with a comment
        self.assertEqual(
            check_comments_presence("test.txt", "# This is a comment"), False
        )

        # Test unsupported file type without a comment
        self.assertEqual(
            check_comments_presence("test.txt", "Hello, World!"), False
        )

if __name__ == "__main__":
    unittest.main()
