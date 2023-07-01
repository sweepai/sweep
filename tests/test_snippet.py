import unittest
from sweepai import Snippet

class TestSnippet(unittest.TestCase):
    def setUp(self):
        self.snippet = Snippet('test_snippet')

    def test_get_snippet(self):
        result = self.snippet.get_snippet()
        self.assertEqual(result, 'test_snippet')

        self.snippet.snippet = 'new_snippet'
        result = self.snippet.get_snippet()
        self.assertEqual(result, 'new_snippet')
</new_file>

