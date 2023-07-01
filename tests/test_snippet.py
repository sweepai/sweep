import unittest
from unittest import mock
from snippet import Snippet

class TestSnippet(unittest.TestCase):
    @mock.patch('snippet.Snippet')
    def test_snippet_valid_content(self, mock_snippet):
        mock_snippet.return_value.__str__.return_value = 'valid snippet'
        snippet = Snippet('valid content', 0, 10)
        result = str(snippet)
        self.assertEqual(result, 'valid snippet')

    @mock.patch('snippet.Snippet')
    def test_snippet_no_content(self, mock_snippet):
        mock_snippet.return_value.__str__.return_value = ''
        snippet = Snippet('', 0, 0)
        result = str(snippet)
        self.assertEqual(result, '')

    @mock.patch('snippet.Snippet')
    def test_snippet_exception_handling(self, mock_snippet):
        mock_snippet.return_value.__str__.side_effect = Exception('error')
        snippet = Snippet('content', 0, 10)
        with self.assertRaises(Exception):
            str(snippet)

if __name__ == '__main__':
    unittest.main()

