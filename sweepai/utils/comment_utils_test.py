import unittest
from unittest.mock import patch
from sweepai.utils.comment_utils import check_comments_presence

class TestCheckCommentsPresence(unittest.TestCase):

    @patch('os.path.splitext', return_value=('.py',))
    def test_check_comments_presence_python(self, mock_splitext):
        file_path = 'test.py'
        new_code = 'print("Hello World") # This is a comment'
        self.assertTrue(check_comments_presence(file_path, new_code))

    @patch('os.path.splitext', return_value=('.js',))
    def test_check_comments_presence_javascript(self, mock_splitext):
        file_path = 'test.js'
        new_code = 'console.log("Hello World"); // This is a comment'
        self.assertTrue(check_comments_presence(file_path, new_code))

    @patch('os.path.splitext', return_value=('.py',))
    def test_check_comments_presence_no_comment(self, mock_splitext):
        file_path = 'test.py'
        new_code = 'print("Hello World")'
        self.assertFalse(check_comments_presence(file_path, new_code))

    @patch('os.path.splitext', return_value=('.unknown',))
    def test_check_comments_presence_unknown_extension(self, mock_splitext):
        file_path = 'test.unknown'
        new_code = 'print("Hello World") # This is a comment'
        self.assertFalse(check_comments_presence(file_path, new_code))

if __name__ == '__main__':
    unittest.main()
