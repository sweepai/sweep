import unittest
from sweepai import generate_new_files

class TestGenerateNewFiles(unittest.TestCase):
    def setUp(self):
        self.generate_new_files = generate_new_files.GenerateNewFiles()

    def test_generate(self):
        input_data = "test"
        result = self.generate_new_files.generate(input_data)
        self.assertIsNotNone(result)

        input_data = ""
        result = self.generate_new_files.generate(input_data)
        self.assertIsNone(result)

    def test_generate_exception(self):
        with self.assertRaises(Exception):
            self.generate_new_files.generate(None)
</new_file>

