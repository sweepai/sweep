import unittest
from sweep import Snippet

class TestSnippet(unittest.TestCase):
    def test_get_snippet(self):
        snippet = Snippet("This is a test snippet.", 0, 23)
        result = snippet.get_snippet()
        self.assertEqual(result, "This is a test snippet.")
</new_file>

