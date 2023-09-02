import os
import tempfile
import unittest

from sweepai.utils.utils import check_file_size

class TestCheckFileSize(unittest.TestCase):
    def test_file_size_less_than_60000_bytes(self):
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp.write(b'0' * 50000)
        self.assertTrue(check_file_size(temp.name))
        os.remove(temp.name)

    def test_file_size_greater_than_60000_bytes(self):
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp.write(b'0' * 70000)
        self.assertFalse(check_file_size(temp.name))
        os.remove(temp.name)

if __name__ == '__main__':
    unittest.main()
