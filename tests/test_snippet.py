import unittest
from src.core.entities import Snippet

class TestSnippet(unittest.TestCase):
    def test_get_snippet_start(self):
        snippet = Snippet(content="line1\nline2\nline3", start=1, end=2)
        output = snippet.get_snippet()
        self.assertEqual(output, "line1\nline2...")

    def test_get_snippet_middle(self):
        snippet = Snippet(content="line1\nline2\nline3", start=2, end=3)
        output = snippet.get_snippet()
        self.assertEqual(output, "...line2\nline3...")

    def test_get_snippet_end(self):
        snippet = Snippet(content="line1\nline2\nline3", start=2, end=3)
        output = snippet.get_snippet()
        self.assertEqual(output, "...line2\nline3")

if __name__ == "__main__":
    unittest.main()