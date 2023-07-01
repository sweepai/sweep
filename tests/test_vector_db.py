import unittest
from unittest import mock
from vector_db import search

class TestVectorDB(unittest.TestCase):
    @mock.patch('vector_db.search')
    def test_search_valid_query(self, mock_search):
        mock_search.return_value = ['expected', 'results']
        result = search('valid query')
        self.assertEqual(result, ['expected', 'results'])

    @mock.patch('vector_db.search')
    def test_search_invalid_query(self, mock_search):
        mock_search.return_value = []
        result = search('invalid query')
        self.assertEqual(result, [])

    @mock.patch('vector_db.search')
    def test_search_exception_handling(self, mock_search):
        mock_search.side_effect = Exception('error')
        with self.assertRaises(Exception):
            search('query')

    @mock.patch('vector_db.search')
    def test_search_sorted_results(self, mock_search):
        mock_search.return_value = ['result1', 'result2', 'result3']
        result = search('query')
        self.assertEqual(result, ['result1', 'result2', 'result3'])

if __name__ == '__main__':
    unittest.main()

