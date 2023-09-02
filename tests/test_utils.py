import unittest
from sweepai.utils.utils import function_name  # replace with actual function name

class TestFileReadingOperation(unittest.TestCase):
    def test_file_size_less_than_60000(self):
        # replace 'file_path' with the path to a test file that is less than 60000 bytes
        self.assertTrue(function_name('file_path'))

    def test_file_size_equal_to_60000(self):
        # replace 'file_path' with the path to a test file that is exactly 60000 bytes
        self.assertTrue(function_name('file_path'))

    def test_file_size_greater_than_60000(self):
        # replace 'file_path' with the path to a test file that is more than 60000 bytes
        self.assertFalse(function_name('file_path'))

if __name__ == '__main__':
    unittest.main()
