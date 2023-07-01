import unittest
from sweep import Snippet

class TestSnippet(unittest.TestCase):

    def setUp(self):
        self.snippet = Snippet("Test Snippet")

    def test_get_snippet(self):
        # Arrange
        expected_output = "Test Snippet"

        # Act
        actual_output = self.snippet.get_snippet()

        # Assert
        self.assertEqual(actual_output, expected_output)

if __name__ == '__main__':
    unittest.main()

