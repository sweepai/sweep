import unittest
import os
from sweep.generate_new_files import GenerateNewFiles

class TestGenerateNewFiles(unittest.TestCase):
    def setUp(self):
        self.generator = GenerateNewFiles()

    def test_file_generation(self):
        # Test file generation
        self.generator.generate('test_file')
        self.assertTrue(os.path.exists('test_file'))

    def test_snippet_extraction(self):
        # Test snippet extraction
        snippet = self.generator.extract_snippet('test_file')
        self.assertIsNotNone(snippet)
</new_file>

