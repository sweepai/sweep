import unittest
from sweep import Snippet

class TestSnippet(unittest.TestCase):
    def test_snippet(self):
        # Assuming Snippet takes a code string and has a method get_code that returns the code
        snippet = Snippet('def add(x, y):\n    return x + y')
        expected_output = 'def add(x, y):\n    return x + y'
        self.assertEqual(snippet.get_code(), expected_output)

if __name__ == '__main__':
    unittest.main()

