import unittest
import os
from sweepai import generate_new_files

class TestGenerateNewFiles(unittest.TestCase):
    def setUp(self):
        self.generator = generate_new_files.Generator()

    def test_file_generation(self):
        self.generator.generate_file('test_file')
        self.assertTrue(os.path.exists('test_file'))

    def test_snippet_creation(self):
        snippet = self.generator.create_snippet('test_snippet')
        self.assertEqual(snippet, 'test_snippet')
</new_file>

