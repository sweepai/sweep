import unittest
from unittest.mock import patch

from sweepai.utils.comment_utils import check_comments_presence


class CommentUtilsTest(unittest.TestCase):
    @patch("os.path.splitext")
    def test_python_file_with_comment(self, mock_splitext):
        mock_splitext.return_value = ("file", ".py")
        new_code = '# This is a comment\nprint("Hello, World!")'
        self.assertEqual(check_comments_presence("file.py", new_code), True)

    @patch("os.path.splitext")
    def test_python_file_without_comment(self, mock_splitext):
        mock_splitext.return_value = ("file", ".py")
        new_code = 'print("Hello, World!")'
        self.assertEqual(check_comments_presence("file.py", new_code), False)

    @patch("os.path.splitext")
    def test_js_file_with_comment(self, mock_splitext):
        mock_splitext.return_value = ("file", ".js")
        new_code = '// This is a comment\nconsole.log("Hello, World!");'
        self.assertEqual(check_comments_presence("file.js", new_code), True)

    @patch("os.path.splitext")
    def test_js_file_without_comment(self, mock_splitext):
        mock_splitext.return_value = ("file", ".js")
        new_code = 'console.log("Hello, World!");'
        self.assertEqual(check_comments_presence("file.js", new_code), False)


if __name__ == "__main__":
    unittest.main()
