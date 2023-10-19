import unittest
from unittest.mock import patch
from sweepai.utils.comment_utils import check_comments_presence

class TestCheckCommentsPresence(unittest.TestCase):

    @patch('os.path.splitext')
    def test_check_comments_presence_with_comment(self, mock_splitext):
        mock_splitext.return_value = ('file', '.py')
        self.assertEqual(check_comments_presence('file.py', '# This is a comment'), True)

    @patch('os.path.splitext')
    def test_check_comments_presence_without_comment(self, mock_splitext):
        mock_splitext.return_value = ('file', '.py')
        self.assertEqual(check_comments_presence('file.py', 'This is not a comment'), False)

    @patch('os.path.splitext')
    def test_check_comments_presence_with_unsupported_file_extension(self, mock_splitext):
        mock_splitext.return_value = ('file', '.unsupported')
        self.assertEqual(check_comments_presence('file.unsupported', 'This is not a comment'), False)

    @patch('os.path.splitext')
    def test_check_comments_presence_with_empty_new_code(self, mock_splitext):
        mock_splitext.return_value = ('file', '.py')
        self.assertEqual(check_comments_presence('file.py', ''), False)

if __name__ == '__main__':
    unittest.main()
