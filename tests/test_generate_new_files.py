import unittest
import os
from sweep.generate_new_files import generate_files

class TestGenerateNewFiles(unittest.TestCase):
    def setUp(self):
        self.exclude_files_present = ["file1", "file2"]
        self.exclude_files_absent = []

    def test_generate_files_exclude_present(self):
        result = generate_files(self.exclude_files_present)
        self.assertIsNotNone(result)

    def test_generate_files_exclude_absent(self):
        result = generate_files(self.exclude_files_absent)
        self.assertIsNotNone(result)

if __name__ == "__main__":
    unittest.main()

