import os
import unittest
from sweepai.utils.utils import check_file_size

class TestCheckFileSize(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_file.txt"
        with open(self.test_file, "w") as f:
            f.write("a" * 60001)

    def tearDown(self):
        os.remove(self.test_file)

    def test_check_file_size(self):
        self.assertFalse(check_file_size(self.test_file))

    def test_check_file_size_small_file(self):
        with open(self.test_file, "w") as f:
            f.write("a" * 59999)
        self.assertTrue(check_file_size(self.test_file))

if __name__ == "__main__":
    unittest.main()
