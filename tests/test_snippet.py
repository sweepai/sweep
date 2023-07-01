import unittest
from sweep.snippet import Snippet

class TestSnippet(unittest.TestCase):
    def setUp(self):
        self.snippet_short = Snippet("short content", 0, 1)
        self.snippet_long = Snippet("long content"*100, 0, 100)
        self.snippet_start_end = Snippet("content", 5, 10)

    def test_content_length(self):
        self.assertEqual(len(self.snippet_short.content), 13)
        self.assertEqual(len(self.snippet_long.content), 1200)

    def test_start_end_positions(self):
        self.assertEqual(self.snippet_start_end.start, 5)
        self.assertEqual(self.snippet_start_end.end, 10)

if __name__ == "__main__":
    unittest.main()

