import unittest
from unittest.mock import patch
from sweep.vector_db import VectorDB

class TestVectorDB(unittest.TestCase):
    @patch('sweep.vector_db.VectorDB.query')
    def test_search(self, mock_query):
        mock_query.return_value = [{'id': 1, 'vector': [1, 2, 3]}]
        db = VectorDB()
        result = db.search([1, 2, 3])
        self.assertEqual(result, [{'id': 1, 'vector': [1, 2, 3]}])

    @patch('sweep.vector_db.VectorDB.query')
    def test_empty_query(self, mock_query):
        mock_query.return_value = []
        db = VectorDB()
        with self.assertRaises(Exception):
            db.search([1, 2, 3])
</new_file>

