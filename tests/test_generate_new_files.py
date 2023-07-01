import unittest
from sweep import generate_new_files

class TestGenerateNewFiles(unittest.TestCase):
    def test_generate_new_files(self):
        # Assuming generate_new_files returns a list of file names
        expected_output = ['file1', 'file2', 'file3']
        self.assertEqual(generate_new_files(), expected_output)

if __name__ == '__main__':
    unittest.main()

