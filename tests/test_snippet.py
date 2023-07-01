import unittest
from sweepai import snippet

class TestSnippet(unittest.TestCase):
    def setUp(self):
        self.snippet = snippet.Snippet()

    def test_get_snippet(self):
        query = "test"
        result = self.snippet.get_snippet(query)
        self.assertIsNotNone(result)

        query = ""
        result = self.snippet.get_snippet(query)
        self.assertIsNone(result)

    def test_get_snippet_exception(self):
        with self.assertRaises(Exception):
            self.snippet.get_snippet(None)
</new_file>

